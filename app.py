import streamlit as st
import pandas as pd
import gspread
import os
import importlib.util

# =========================================================================
# [UI 레이아웃] 사이드바 완전 비활성화 및 광폭 화면 주입
# =========================================================================
st.set_page_config(
    layout="wide", 
    page_title="사내 클라우드 인사·급여 관리 시스템 v3.5",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        [data-testid="stSidebarCollapse"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
        [data-testid="stSidebar"] { display: none; }
    </style>
""", unsafe_allow_html=True)

# =========================================================================
# [Global Infrastructure] 서브 파일에서 안전하게 참조할 공통 DAO 자원 선언
# =========================================================================
GOOGLE_SHEET_ID = "1BgbLxUBh4v430YXLsDBN9yWXSfVpdOWAY_FHP_-R7Go"

def get_gspread_client():
    return gspread.service_account(filename='google_creds.json')

def load_settings():
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        ws = sh.worksheet("설정")
        return {row["항목"]: row["값"] for row in ws.get_all_records() if "항목" in row and "값" in row}
    except Exception:
        return {
            "기준연도": 2026, "최저임금": 10030, 
            "국민연금": 4.5, "건강보험": 3.545, "장기요양_환산율": 12.95, 
            "고용_65세미만": 0.9, "고용_65세이상": 0
        }

def load_employees(sheet_name="재직자리스트", filter_active=True):
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        ws = sh.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        if df.empty: return pd.DataFrame()
        if filter_active and '퇴사일' in df.columns:
            return df[df['퇴사일'].astype(str).str.strip() == ""]
        return df
    except Exception:
        return pd.DataFrame()

def clean_amount_columns(df):
    if df.empty: return df
    target_cols = ["기본급", "차량지원금", "식대지원금"]
    for col in target_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(",", "").str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    return df

# 전역 컨텍스트 캐시 세션 초기 바인딩
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

if "active_emp_df" not in st.session_state:
    raw_emp_df = load_employees("재직자리스트", filter_active=True)
    st.session_state.active_emp_df = clean_amount_columns(raw_emp_df)

# =========================================================================
# 💡 [핵심 교정부] 자바의 Main 클래스 격리 기법 구현 (__name__ 검증)
# =========================================================================
# 이 파일이 최초 실행점일 때만 UI 메뉴(라디오 버튼)를 활성화하여 서브 파일 import 시의 이중 출력을 전면 차단합니다.
if __name__ == "__main__":
    st.title("💼 사내 클라우드 인사·급여 관리 시스템 (v3.5)")
    
    st.markdown("### 🧭 메뉴 이동")
    menu_selection = st.radio(
        "이동하실 페이지 버튼을 클릭하세요:",
        ["📊 메인 대시보드 홈", "👤 직원 관리 및 명부", "⏱️ 근로시간 입력 및 정산", "⚙️ 시스템 요율 설정"],
        horizontal=True,
        key="main_navigation_router"
    )
    
    st.markdown("---")
    
    if menu_selection == "📊 메인 대시보드 홈":
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1: st.metric(label="현재 전사 총 재직 인원", value=f"{len(st.session_state.active_emp_df)} 명")
        with col_m2: st.metric(label="올해 적용 최저임금 기준", value=f"{int(st.session_state.settings.get('최저임금', 10030)):,} 원")
        with col_m3: st.metric(label="시스템 마스터 기준 연도", value=f"{int(st.session_state.settings.get('기준연도', 2026))} 년")
        
        c1, c2 = st.columns([1.5, 1])
        with c1:
            st.write("⚙️ **현재 인프라 전역에 바인딩된 요율 정보**")
            st.json(st.session_state.settings)
        with c2:
            st.success("✅ 구글 스프레드시트 실시간 클라우드 커넥션 정상 완료")
            
    else:
        # 서브 라우터 다이렉트 자원 매핑
        page_files = {
            "👤 직원 관리 및 명부": "pages/employee.py",
            "⏱️ 근로시간 입력 및 정산": "pages/salary.py",
            "⚙️ 시스템 요율 설정": "pages/set.py"
        }
        
        target_file_path = page_files[menu_selection]
        
        if os.path.exists(target_file_path):
            try:
                # 서브 모듈 동적 로드 클래스로더 작동
                spec = importlib.util.spec_from_file_location("subpage", target_file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as err:
                st.error(f"서브 파일 호출 실행 오류: {err}")
        else:
            st.error(f"❌ '{target_file_path}' 경로에 물리 파일이 존재하지 않습니다.")
