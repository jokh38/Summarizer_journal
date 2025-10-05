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

# 키워드 추출을 위한 의학물리 용어 사전
MEDICAL_PHYSICS_KEYWORDS = [
    "radiation therapy", "radiotherapy", "dose", "dosimetry", "treatment planning",
    "IMRT", "VMAT", "stereotactic", "brachytherapy", "Monte Carlo", "CT", "MRI",
    "linear accelerator", "beam", "phantom", "QA", "quality assurance", "IGRT",
    "patient safety", "machine learning", "AI", "deep learning", "proton therapy",
    "imaging", "segmentation", "contouring", "organ at risk", "OAR", "PTV", "GTV"
]

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

# 키워드 추출 함수
def extract_keywords(title, abstract):
    found_keywords = []
    combined_text = (title + " " + abstract).lower()
    
    for keyword in MEDICAL_PHYSICS_KEYWORDS:
        if keyword.lower() in combined_text:
            found_keywords.append(keyword)
    
    return found_keywords[:5]  # 최대 5개 키워드 반환

# Ollama API를 사용한 텍스트 요약
def summarize_with_ollama(title, text, model= MODEL_ollama, max_length=1000):
    try:
        ollama_url = "http://localhost:11434/api/generate"
        prompt = f"다음 논문의 초록을 한국어로 요약해줘. 논문의 핵심 내용과 중요한 발견 모두 포함하도록 자연스럽게 요약할 것:\n\n제목: {title}\n\n초록: {text}"
        
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
    return journals

# MD 출력 파일 시작 함수
def start_md_file(file_path):
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f'''# 논문 요약 보고서

**생성 일시:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

''')

# MD 출력 파일 종료 함수
def end_md_file(file_path):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write('\n---\n\n**요약 작업 완료**\n')

# 저널 섹션 시작 함수
def start_journal_section(file_path, journal_name):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f'\n## {journal_name}\n\n<details>\n<summary>논문 목록 보기</summary>\n\n')

# 저널 섹션 종료 함수
def end_journal_section(file_path):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write('\n</details>\n\n --- \n\n')

# 논문 정보 추가 함수 (수정된 버전)
def add_paper_to_md(file_path, paper_info, summary, keywords):
    with open(file_path, 'a', encoding='utf-8') as f:
        keywords_str = ', '.join([f'`{kw}`' for kw in keywords]) if keywords else '없음'
        f.write(f'''### {paper_info['title']}
- [ ] ** {paper_info['title']} **
**출판일:** {paper_info['published']}

<details>
<summary>-내용보기-</summary>

**링크:** [{paper_info['link']}]({paper_info['link']})
**키워드:** {keywords_str}

**영문 초록**
{summary['english_abstract']}

**한글 요약**
{summary['korean_summary']}

</details>

''')

# 메인 함수
def main():
    today = datetime.datetime.now().strftime('%Y%m%d')
    output_file = f"papers_summary_{today}.md"
    
    try:
        # 저널 목록 로드
        journals = load_journal_list()
        
        # 진행 상태 로드
        progress = load_progress()
        
        # MD 파일 시작
        start_md_file(output_file)
        
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
                
                # 키워드 추출
                keywords = extract_keywords(paper_info['title'], paper_info['abstract'])
                
                # Ollama를 사용한 요약 (제목과 초록 함께 전송)
                summary = summarize_with_ollama(paper_info['title'], paper_info['abstract'])
                
                # MD에 논문 정보 추가
                add_paper_to_md(output_file, paper_info, summary, keywords)
                
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
        
        # MD 파일 종료
        end_md_file(output_file)
        
        # 진행 상태 저장
        save_progress(progress)
        logger.info(f"요약 작업 완료. 결과 파일: {output_file}")
        
        # Windows에서 MD 파일 열기
        os.system(f"start {output_file}")
        
        # Ollama 모델 언로드
        unload_ollama_model()
        
    except Exception as e:
        logger.error(f"처리 중 오류 발생: {e}")
        # 오류 발생해도 모델 언로드 시도
        unload_ollama_model()

if __name__ == "__main__":
    main()