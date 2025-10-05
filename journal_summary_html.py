import feedparser
import json
import os
import datetime
import requests
import re
from bs4 import BeautifulSoup
import time
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("paper_summarizer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Ollama 모델 선택
MODEL_ollama = "exaone3.5:7.8b"

# Ollama 모델 로드 함수
def load_ollama_model(model=MODEL_ollama):
    try:
        ollama_url = "http://localhost:11434/api/generate"
        payload = {
            "model": model,
            "stream": False,
            "options": {
                "num_ctx": 4096,  # 컨텍스트 윈도우 크기
                "num_predict": 2048,  # 생성할 최대 토큰 수 증가
                "temperature": 0.7,  # 창의성 조절
                "reset": True  # 대화 컨텍스트 초기화
            }
        }
        
        response = requests.post(ollama_url, json=payload)
        
        if response.status_code == 200:
            logger.info(f"Ollama 모델 '{model}' 로드 성공")
        else:
            logger.error(f"Ollama 모델 로드 실패: {response.status_code}, {response.text}")
    except Exception as e:
        logger.error(f"Ollama 모델 로드 중 오류 발생: {e}")

# Ollama 모델 언로드 함수
def unload_ollama_model(model=MODEL_ollama):
    try:
        ollama_url = "http://localhost:11434/api/delete"
        payload = {
            "name": model
        }
        
        response = requests.delete(ollama_url, json=payload)
        
        if response.status_code == 200:
            logger.info(f"Ollama 모델 '{model}' 언로드 성공")
        else:
            logger.error(f"Ollama 모델 언로드 실패: {response.status_code}, {response.text}")
    except Exception as e:
        logger.error(f"Ollama 모델 언로드 중 오류 발생: {e}")

# Ollama API를 사용한 텍스트 요약
def summarize_with_ollama(title, text, model= MODEL_ollama, max_length=1000):
    try:
        ollama_url = "http://localhost:11434/api/generate"
        prompt = f"다음 논문의 제목과 초록을 한국어로 요약해줘. 논문의 핵심 내용과 중요한 발견 모두 포함하도록 자연스럽게 요약할 것:\n\n제목: {title}\n\n초록: {text}"
        
        # 각 요청을 새로운 대화로 처리하여 컨텍스트 누적 방지
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 4096,  # 컨텍스트 윈도우 크기
                "num_predict": 2048,  # 생성할 최대 토큰 수 증가
                "temperature": 0.6,  # 창의성 조절
                "reset": True  # 대화 컨텍스트 초기화
            }
        }
        
        response = requests.post(ollama_url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            return {
                'english_abstract': text,
                'korean_summary': result.get('response', '요약 실패')
            }
        else:
            logger.error(f"Ollama API 오류: {response.status_code}, {response.text}")
            return {
                'english_abstract': text,
                'korean_summary': summarize_text_fallback(text, max_length)
            }
    except Exception as e:
        logger.error(f"Ollama 요약 중 오류 발생: {e}")
        return {
            'english_abstract': text,
            'korean_summary': summarize_text_fallback(text, max_length)
        }

# 폴백용 간단한 텍스트 요약 (Ollama 사용 불가시)
def summarize_text_fallback(text, max_length=300):
    # 간단한 요약: 첫 부분 반환
    return text[:max_length] + "..."

# 논문 정보 추출 함수 (사이트별 구조에 맞게 구현)
def extract_paper_info(entry, journal_url):
    try:
        title = entry.get('title', '제목 없음')
        link = entry.get('link', '')
        published = entry.get('published', datetime.datetime.now().strftime('%Y-%m-%d'))
        
        # 기본 초록 추출 시도
        abstract = entry.get('summary', '')
        
        # 사이트별 구조에 따른 초록 추출 로직
        if not abstract and link:
            abstract = extract_abstract(link, journal_url)
        
        # HTML 태그 제거
        if abstract:
            abstract = re.sub(r'<.*?>', '', abstract)
            abstract = abstract.strip()
        
        return {
            'title': title,
            'link': link,
            'published': published,
            'abstract': abstract
        }
    except Exception as e:
        logger.error(f"논문 정보 추출 중 오류 발생: {e}")
        return {
            'title': entry.get('title', '제목 없음'),
            'link': entry.get('link', ''),
            'published': entry.get('published', datetime.datetime.now().strftime('%Y-%m-%d')),
            'abstract': '초록 추출 실패'
        }

# 각 저널별 추출 로직 사전 정의
JOURNAL_EXTRACTORS = {
    "meddos.org": {
        "selector": "div.abstract",
        "type": "class"
    },
    "physicamedica.com": {
        "selector": "div.abstract",
        "type": "class"
    },
    "wiley.com": {
        "selector": "div.abstract-content",
        "type": "class"
    },
    "redjournal.org": {
        "selector": "div.abstractSection",
        "type": "class"
    },
    "ro-journal.com": {
        "selector": "div#abstract",
        "type": "id"
    }
}

def extract_abstract(link, journal_url):
    """
    주어진 링크에서 해당 저널의 추출 로직에 따라 초록을 추출합니다.
    """
    try:
        # 저널 도메인 추출
        domain = None
        for key in JOURNAL_EXTRACTORS:
            if key in journal_url:
                domain = key
                break
        
        if not domain:
            logger.error(f"알 수 없는 저널 도메인: {journal_url}")
            return ""
            
        # 추출 로직 정보 가져오기
        extractor = JOURNAL_EXTRACTORS[domain]
        
        # 페이지 요청
        response = requests.get(link, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 선택자에 따라 요소 찾기
        if extractor["type"] == "class":
            abstract_div = soup.find('div', class_=extractor["selector"][4:])
        else:  # id
            abstract_div = soup.find('div', id=extractor["selector"][1:])
        
        if abstract_div:
            return abstract_div.get_text().strip()
        return ""
    except Exception as e:
        logger.error(f"초록 추출 실패: {e}")
        return ""

# 진행 상태 파일 로드
def load_progress():
    progress_file = "paper_progress.json"
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"진행 상태 로드 실패: {e}")
    return {}

# 진행 상태 저장
def save_progress(progress):
    progress_file = "paper_progress.json"
    try:
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"진행 상태 저장 실패: {e}")

# 논문 사이트 목록 로드
def load_journal_list(file_path="journal_list.txt"):
    journals = {}
    if not os.path.exists(file_path):
        # 기본 저널 리스트 생성
        journals = {
            "Medical Dosimetry": "http://www.meddos.org/current.rss",
            "Physica Medica": "http://www.physicamedica.com/current.rss",
            "Journal of Applied Clinical Medical Physics": "https://aapm.onlinelibrary.wiley.com/feed/15269914/most-recent",
            "Medical Physics": "https://aapm.onlinelibrary.wiley.com/feed/24734209/most-recent",
            "Physics in Medicine and Biology": "https://iopscience.iop.org/journal/rss/0031-9155",
            "International Journal of Radiation Oncology, Biology, Physics": "https://www.redjournal.org/current.rss",
            "Radiation Oncology": "http://www.ro-journal.com/latest/rss"
        }
        # 파일 저장
        with open(file_path, 'w', encoding='utf-8') as f:
            for name, url in journals.items():
                f.write(f"{name}\n{url}\n")
    else:
        # 파일에서 로드
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i in range(0, len(lines), 2):
                if i+1 < len(lines):
                    name = lines[i].strip()
                    url = lines[i+1].strip()
                    journals[name] = url
    
    return journals

# HTML 출력 파일 시작 함수
def start_html_file(file_path):
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>논문 요약 보고서</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; color: #333; }
        h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
        h2 { color: #3498db; border-bottom: 2px solid #3498db; padding-bottom: 5px; margin-top: 30px; cursor: pointer; }
        h2:after { content: " ▼"; font-size: 0.8em; }
        h2.collapsed:after { content: " ▶"; font-size: 0.8em; }
        h3 { color: #2c3e50; margin-top: 20px; }
        .paper { background-color: #f9f9f9; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 25px; border-radius: 0 5px 5px 0; }
        .meta { color: #7f8c8d; margin: 10px 0; font-size: 0.9em; }
        .abstract { margin: 15px 0; text-align: justify; }
        .summary { background-color: #eef9fd; padding: 15px; border-radius: 5px; margin-top: 15px; }
        a { color: #3498db; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .journal-content { display: block; }
        .collapsed + .journal-content { display: none; }
    </style>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // 모든 저널 제목에 클릭 이벤트 추가
            var headers = document.querySelectorAll('h2');
            headers.forEach(function(header) {
                header.addEventListener('click', function() {
                    this.classList.toggle('collapsed');
                    var content = this.nextElementSibling;
                    if (content && content.classList.contains('journal-content')) {
                        if (this.classList.contains('collapsed')) {
                            content.style.display = 'none';
                        } else {
                            content.style.display = 'block';
                        }
                    }
                });
            });
        });
    </script>
</head>
<body>
    <h1>논문 요약 보고서</h1>
    <p>생성 일시: %s</p>
''' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

# HTML 출력 파일 종료 함수
def end_html_file(file_path):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write('''
</body>
</html>
''')

# 저널 섹션 시작 함수
def start_journal_section(file_path, journal_name):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f'\n    <h2>{journal_name}</h2>\n    <div class="journal-content">\n')

# 저널 섹션 종료 함수
def end_journal_section(file_path):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write('    </div>\n')

# 논문 정보 추가 함수
def add_paper_to_html(file_path, paper_info, summary):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"""
        <div class="paper">
            <h3>{paper_info['title']}</h3>
            <div class="meta">
                <span>출판일: {paper_info['published']}</span>
                <span>링크: <a href="{paper_info['link']}" target="_blank">원문 보기</a></span>
            </div>
            <div class="abstract">
                <h4>영문 초록</h4>
                <p>{summary['english_abstract']}</p>
                <h4>한글 요약</h4>
                <p>{summary['korean_summary']}</p>
            </div>
        </div>
""")


# 메인 함수
def main():
    today = datetime.datetime.now().strftime('%Y%m%d')
    output_file = f"papers_summary_{today}.html"
    
    try:
        # 저널 목록 로드
        journals = load_journal_list()
        
        # 진행 상태 로드
        progress = load_progress()
        
        # HTML 파일 시작
        start_html_file(output_file)
        
        for journal_name, journal_url in journals.items():
            logger.info(f"{journal_name} 처리 시작")
            
            # 저널 섹션 시작
            start_journal_section(output_file, journal_name)
            
            # RSS 피드 파싱
            feed = feedparser.parse(journal_url)
            
            # 저널별 마지막 처리 시간 확인
            last_processed = progress.get(journal_name, {}).get('last_processed', '')
            
            # 처리할 항목 수 계산
            total_entries = len(feed.entries)
            logger.info(f"{journal_name}: 총 {total_entries}개 항목 발견")
            
            new_papers = []
            for i, entry in enumerate(feed.entries):
                entry_id = entry.get('id', entry.get('link', ''))
                
                # 이미 처리된 항목인지 확인
                if last_processed and (entry_id in progress.get(journal_name, {}).get('processed_ids', [])):
                    continue
                
                # 진행 상황 표시
                logger.info(f"{journal_name}: {i+1}/{total_entries} 처리 중")
                
                # 논문 정보 추출
                paper_info = extract_paper_info(entry, journal_url)
                
                # 초록이 없는 경우 건너뛰기
                if not paper_info['abstract']:
                    logger.warning(f"초록 없음: {paper_info['title']}")
                    continue
                
                # Ollama를 사용한 요약 (제목과 초록 함께 전송)
                summary = summarize_with_ollama(paper_info['title'], paper_info['abstract'])
                
                # HTML에 논문 정보 추가
                add_paper_to_html(output_file, paper_info, summary)
                
                # 처리된 항목 추적
                new_papers.append(entry_id)
                
                # 과도한 요청 방지를 위한 딜레이
                time.sleep(1)
            
            # 진행 상태 업데이트
            if journal_name not in progress:
                progress[journal_name] = {}
            
            processed_ids = progress.get(journal_name, {}).get('processed_ids', [])
            progress[journal_name] = {
                'last_processed': datetime.datetime.now().isoformat(),
                'processed_ids': processed_ids + new_papers
            }        
                        
            # 처리 완료 후 저널 섹션 종료 추가
            end_journal_section(output_file)
            
            logger.info(f"{journal_name}: {len(new_papers)}개 새 논문 처리 완료")
        
        # HTML 파일 종료
        end_html_file(output_file)
        
        # 진행 상태 저장
        save_progress(progress)
        logger.info(f"요약 작업 완료. 결과 파일: {output_file}")
        
        # Windows에서 HTML 파일 열기
        os.system(f"start {output_file}")
        
        # Ollama 모델 언로드
        unload_ollama_model()
        
    except Exception as e:
        logger.error(f"처리 중 오류 발생: {e}")
        # 오류 발생해도 모델 언로드 시도
        unload_ollama_model()

if __name__ == "__main__":
    main()