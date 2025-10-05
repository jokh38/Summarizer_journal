"""
Output generation module for creating formatted reports.

Supports multiple output formats (HTML, Markdown) with a common interface.
Each format generator handles file creation, section management, and styling.
"""

import datetime
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseOutputGenerator(ABC):
    """
    Abstract base class for output generators.

    Defines the interface that all output format generators must implement.
    """
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.file_path = None

    @abstractmethod
    def start_file(self):
        pass

    @abstractmethod
    def start_journal_section(self, journal_name: str):
        pass

    @abstractmethod
    def add_paper(self, paper_info: Dict[str, Any], summary: Dict[str, str], keywords: List[str]):
        pass

    @abstractmethod
    def end_journal_section(self):
        pass

    @abstractmethod
    def end_file(self):
        pass

class HtmlGenerator(BaseOutputGenerator):
    def start_file(self):
        today = datetime.datetime.now().strftime('%Y%m%d')
        self.file_path = os.path.join(self.output_dir, f"papers_summary_{today}.html")
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write(f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>논문 요약 보고서</title><style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; color: #333; }}
h1 {{ color: #2c3e50; text-align: center; margin-bottom: 30px; }}
h2 {{ color: #3498db; border-bottom: 2px solid #3498db; padding-bottom: 5px; margin-top: 30px; cursor: pointer; }}
h2:after {{ content: " ▼"; font-size: 0.8em; }}
h2.collapsed:after {{ content: " ▶"; font-size: 0.8em; }}
h3 {{ color: #2c3e50; margin-top: 20px; }}
.paper {{ background-color: #f9f9f9; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 25px; border-radius: 0 5px 5px 0; }}
.meta {{ color: #7f8c8d; margin: 10px 0; font-size: 0.9em; }}
.abstract {{ margin: 15px 0; text-align: justify; }}
.summary {{ background-color: #eef9fd; padding: 15px; border-radius: 5px; margin-top: 15px; }}
a {{ color: #3498db; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.journal-content {{ display: block; }}
.collapsed + .journal-content {{ display: none; }}
</style><script>document.addEventListener('DOMContentLoaded',function(){document.querySelectorAll('h2').forEach(function(h){h.addEventListener('click',function(){this.classList.toggle('collapsed');var c=this.nextElementSibling;if(c&&c.classList.contains('journal-content')){c.style.display=this.classList.contains('collapsed')?'none':'block';}});});});</script></head><body><h1>논문 요약 보고서</h1><p>생성 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>''')

    def start_journal_section(self, journal_name: str):
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write(f'\n<h2>{journal_name}</h2>\n<div class="journal-content">\n')

    def add_paper(self, paper_info: Dict[str, Any], summary: Dict[str, str], keywords):
        with open(self.file_path, 'a', encoding='utf-8') as f:
            kw_html = ''
            if keywords:
                kw_html = '<p>키워드: ' + ', '.join(keywords) + '</p>'
            f.write(f'''<div class="paper"><h3>{paper_info['title']}</h3><div class="meta"><span>출판일: {paper_info['published']}</span> <span>링크: <a href="{paper_info['link']}" target="_blank">원문 보기</a></span></div><div class="abstract"><h4>영문 초록</h4><p>{summary['english_abstract']}</p><h4>한글 요약</h4><p>{summary['korean_summary']}</p>{kw_html}</div></div>''')

    def end_journal_section(self):
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write('</div>')

    def end_file(self):
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write('</body></html>')

class MarkdownGenerator(BaseOutputGenerator):
    def start_file(self):
        today = datetime.datetime.now().strftime('%Y%m%d')
        self.file_path = os.path.join(self.output_dir, f"papers_summary_{today}.md")
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write(f"""# 논문 요약 보고서\n\n**생성 일시:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n""")

    def start_journal_section(self, journal_name: str):
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write(f"\n## {journal_name}\n\n<details>\n<summary>논문 목록 보기</summary>\n\n")

    def add_paper(self, paper_info: Dict[str, Any], summary: Dict[str, str], keywords):
        kw_md = ', '.join([f'`{k}`' for k in keywords]) if keywords else '없음'
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write(f"""### {paper_info['title']}\n- [ ] **{paper_info['title']}**\n**출판일:** {paper_info['published']}\n\n<details>\n<summary>-내용보기-</summary>\n\n**링크:** [{paper_info['link']}]({paper_info['link']})\n**키워드:** {kw_md}\n\n**영문 초록**\n{summary['english_abstract']}\n\n**한글 요약**\n{summary['korean_summary']}\n\n</details>\n\n""")

    def end_journal_section(self):
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write('\n</details>\n\n---\n\n')

    def end_file(self):
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write('\n---\n\n**요약 작업 완료**\n')


def build_output_generator(fmt: str, output_dir: str) -> BaseOutputGenerator:
    if fmt == 'html':
        return HtmlGenerator(output_dir)
    if fmt == 'md':
        return MarkdownGenerator(output_dir)
    raise ValueError(f"Unsupported output format: {fmt}")
