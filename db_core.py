import streamlit as st
import pandas as pd
import gspread

# 💡 이 부분이 정확하게 들어가 있어야 서브 파일들이 읽어올 수 있습니다!
GOOGLE_SHEET_ID = "1BgbLxUBh4v430YXLsDBN9yWXSfVpdOWAY_FHP_-R7Go"

# db_core.py 파일 내부 함수 수정
def get_gspread_client():
    try:
        # 💡 로컬 컴퓨터에서 돌릴 때는 기존처럼 파일을 읽음
        return gspread.service_account(filename='google_creds.json')
    except Exception:
        # 💡 [클라우드 전용 보안 코드] 깃허브에 파일이 없을 때, 인터넷 보안 공간(Secrets)에서 글자 형태로 직접 읽어옴
        import json
        creds_dict = dict(st.secrets["google_creds"])
        return gspread.service_account_from_dict(creds_dict)

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
