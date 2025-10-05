"""
Journal Paper Summarizer - Main Entry Point

This module orchestrates the entire paper summarization workflow including:
- Configuration loading and validation
- Journal RSS feed processing
- Abstract extraction and translation
- Output report generation
"""

import argparse
import logging
import logging.handlers
import os
import sys
import webbrowser
from pathlib import Path

from src.config_loader import load_config, ConfigError
from src.translator import build_translator
from src.progress_manager import ProgressManager
from src.journal_processor import JournalProcessor
from src.output_generator import build_output_generator


def setup_logging(log_dir: str, level: str):
    """
    Setup logging with file rotation and console output.

    Args:
        log_dir: Directory to store log files
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'paper_summarizer.log')

    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler with rotation (10MB per file, keep 5 files)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def parse_args():
    p = argparse.ArgumentParser(description='Journal Paper Summarizer')
    p.add_argument('--config', help='Config file path', default=None)
    p.add_argument('--format', help='Override output format (html|md)', default=None)
    p.add_argument('--journals', nargs='*', help='Specific journal names to process', default=None)
    p.add_argument('--force', action='store_true', help='Ignore previous progress and reprocess all')
    p.add_argument('--dry-run', action='store_true', help='Simulate without translation/output writing')
    return p.parse_args()


def main():
    args = parse_args()
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config.get('log_dir', default='logs'), config.get('log_level', default='INFO'))
    logger = logging.getLogger('main')

    out_format = args.format or config.get('output_format', default='html')
    output_dir = config.get('output_dir', default='output')

    translator = build_translator(config)
    progress_path = config.get('progress', 'file_path', default='data/progress.json')
    pm = ProgressManager(progress_path,
                         backup_count=config.get('progress', 'backup_count', default=5),
                         retention_days=config.get('progress', 'retention_days', default=90))

    jp = JournalProcessor(config.data)
    journal_list_file = config.get('journals', 'list_file', default='journal_list.txt')
    journals = jp.load_journals(journal_list_file)

    if args.journals:
        # filter by provided names
        journals = {k: v for k, v in journals.items() if k in args.journals}

    og = build_output_generator(out_format, output_dir)
    if not args.dry_run:
        og.start_file()

    processed_count = 0

    for journal_name, journal_url in journals.items():
        logger.info(f"{journal_name} 처리 시작")
        if not args.dry_run:
            og.start_journal_section(journal_name)
        entries = list(jp.iter_papers(journal_name, journal_url))
        for entry in entries:
            entry_id = entry.get('id', entry.get('link', ''))
            if not args.force and pm.is_processed(journal_name, entry_id):
                continue
            paper_info = jp.extract_paper_info(entry, journal_url)
            if not paper_info['abstract']:
                logger.warning(f"초록 없음: {paper_info['title']}")
                continue
            keywords = jp.extract_keywords(paper_info['title'], paper_info['abstract'])
            if args.dry_run:
                summary = {'english_abstract': paper_info['abstract'], 'korean_summary': '(dry-run)'}
            else:
                summary = translator.translate(paper_info['title'], paper_info['abstract'])
                og.add_paper(paper_info, summary, keywords)
            pm.add_processed(journal_name, entry_id)
            processed_count += 1
        if not args.dry_run:
            og.end_journal_section()

    pm.cleanup()
    pm.save()
    if not args.dry_run:
        og.end_file()

    logger.info(f"처리 완료. 총 처리 논문 수: {processed_count}")

    # Cross-platform file opening
    if not args.dry_run and og.file_path and os.path.exists(og.file_path):
        try:
            logger.info(f"Opening output file: {og.file_path}")
            webbrowser.open('file://' + os.path.abspath(og.file_path))
        except Exception as e:
            logger.warning(f"Could not open output file automatically: {e}")
            logger.info(f"Output file saved to: {og.file_path}")


if __name__ == '__main__':
    main()
