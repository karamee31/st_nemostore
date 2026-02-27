import streamlit as st
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go
from streamlit_folium import folium_static
import folium
from PIL import Image
import requests
from io import BytesIO
import koreanize_matplotlib

# 페이지 설정
st.set_page_config(
    page_title="네모 상가 매물 분석 대시보드",
    page_icon="🏪",
    layout="wide"
)

# --- 데이터 처리 함수 ---

def convert_to_won(val):
    """
    JSON 값을 원 단위로 변환 (규칙: JSON값 * 10,000)
    예: 45000 -> 450,000,000
    """
    if pd.isna(val) or val is None:
        return 0
    return int(val) * 10000

@st.cache_data
def load_data():
    """
    JSON 데이터를 로드하고 전처리를 수행합니다.
    """
    with open('nemostore/api_sample.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data['items'])
    
    # 금액 변환 (원 단위)
    df['deposit_won'] = df['deposit'].apply(convert_to_won)
    df['monthlyRent_won'] = df['monthlyRent'].apply(convert_to_won)
    df['premium_won'] = df['premium'].apply(convert_to_won)
    df['maintenanceFee_won'] = df['maintenanceFee'].apply(convert_to_won)
    
    # 투자 지표 계산
    # 초기 투자금 = 보증금 + 권리금
    df['total_investment'] = df['deposit_won'] + df['premium_won']
    
    # 월 임대 수익률 (%) - 단순 계산 (권리금 등 부대비용 제외 시의 보증금 대비 월세는 의미가 적으므로, 총 투자금 대비 연환산 월세로 계산)
    # 여기서는 상가 분석의 일반적 지표인 (연월세 / 초기투자금) * 100 활용
    df['roi'] = (df['monthlyRent_won'] * 12 / df['total_investment'].replace(0, float('nan'))) * 100
    
    # 회수 기간 (년) = 초기 투자금 / (월세 * 12)
    df['payback_period'] = df['total_investment'] / (df['monthlyRent_won'] * 12).replace(0, float('nan'))
    
    # 면적당 권리금 등 추가 지표
    df['premium_per_size'] = df['premium_won'] / df['size']
    
    return df

# --- 메인 대시보드 로직 ---

def main():
    st.title("🏪 상가 매물 분석 대시보드")
    st.markdown("---")

    try:
        df = load_data()
    except FileNotFoundError:
        st.error("데이터 파일을 찾을 수 없습니다. (nemostore/api_sample.json)")
        return

    # --- 사이드바 필터 ---
    st.sidebar.header("🔍 필터 옵션")
    
    # 업종 필터
    business_types = sorted(df['businessLargeCodeName'].unique())
    selected_business = st.sidebar.multiselect("업종 선택", business_types, default=business_types)
    
    # 층수 필터
    floors = sorted(df['floor'].unique())
    selected_floors = st.sidebar.multiselect("층 선택", floors, default=floors)
    
    # 금액 범위 필터 (원 단위)
    rent_range = st.sidebar.slider(
        "월세 범위 (만원)", 
        0, int(df['monthlyRent'].max()), (0, int(df['monthlyRent'].max()))
    )
    
    deposit_range = st.sidebar.slider(
        "보증금 범위 (만원)", 
        0, int(df['deposit'].max()), (0, int(df['deposit'].max()))
    )
    
    size_range = st.sidebar.slider(
        "면적 범위 (㎡)", 
        0.0, float(df['size'].max()), (0.0, float(df['size'].max()))
    )
    
    # 필터링 적용
    filtered_df = df[
        (df['businessLargeCodeName'].isin(selected_business)) &
        (df['floor'].isin(selected_floors)) &
        (df['monthlyRent'].between(rent_range[0], rent_range[1])) &
        (df['deposit'].between(deposit_range[0], deposit_range[1])) &
        (df['size'].between(size_range[0], size_range[1]))
    ]

    # --- KPI 요약 카드 ---
    st.subheader("📊 주요 시장 지표 (평균)")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    def format_won(val):
        if val >= 100000000:
            return f"{val/100000000:.1f}억"
        return f"{val/10000:,.0f}만"

    with col1:
        avg_rent = filtered_df['monthlyRent_won'].mean()
        st.metric("평균 월세", format_won(avg_rent))
    with col2:
        avg_deposit = filtered_df['deposit_won'].mean()
        st.metric("평균 보증금", format_won(avg_deposit))
    with col3:
        avg_premium = filtered_df['premium_won'].mean()
        st.metric("평균 권리금", format_won(avg_premium))
    with col4:
        avg_area_price = filtered_df['areaPrice'].mean()
        st.metric("평균 평단가", f"{avg_area_price:,.0f}만")
    with col5:
        avg_maint = filtered_df['maintenanceFee_won'].mean()
        st.metric("평균 관리비", format_won(avg_maint))

    st.markdown("---")

    # --- 시각화 섹션 ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("💰 월세 분포")
        fig_hist = px.histogram(filtered_df, x="monthlyRent", nbins=20, 
                               title="월세 분포 (만원 단위)",
                               labels={"monthlyRent": "월세(만원)", "count": "매물 수"},
                               color_discrete_sequence=['#636EFA'])
        st.plotly_chart(fig_hist, use_container_width=True)

        st.subheader("📍 면적 vs 월세")
        fig_scatter_size = px.scatter(filtered_df, x="size", y="monthlyRent", 
                                     color="businessLargeCodeName",
                                     hover_data=["title", "floor"],
                                     title="면적 대비 월세 비중",
                                     labels={"size": "면적(㎡)", "monthlyRent": "월세(만원)"})
        st.plotly_chart(fig_scatter_size, use_container_width=True)

    with col_right:
        st.subheader("⚖️ 보증금 vs 월세")
        fig_scatter_dep = px.scatter(filtered_df, x="deposit", y="monthlyRent",
                                    size="size", color="areaPrice",
                                    hover_data=["title"],
                                    title="보증금 대비 월세 산점도 (크기: 면적)",
                                    labels={"deposit": "보증금(만원)", "monthlyRent": "월세(만원)"})
        st.plotly_chart(fig_scatter_dep, use_container_width=True)

        st.subheader("📈 평단가 분포 (박스플롯)")
        fig_box = px.box(filtered_df, y="areaPrice", points="all",
                        title="업종별 평단가 분포",
                        x="businessLargeCodeName",
                        labels={"areaPrice": "평단가(만원)", "businessLargeCodeName": "업종"})
    st.plotly_chart(fig_box, use_container_width=True)

    st.markdown("---")

    # --- 매물 테이블 ---
    st.subheader("📋 전체 매물 목록")
    display_cols = [
        'title', 'businessMiddleCodeName', 'size', 'floor', 
        'deposit_won', 'monthlyRent_won', 'premium_won', 'maintenanceFee_won',
        'areaPrice', 'nearSubwayStation'
    ]
    # 테이블용 데이터프레임 정리
    table_df = filtered_df[display_cols].copy()
    table_df.columns = [
        '제목', '업종', '면적(㎡)', '층', 
        '보증금(원)', '월세(원)', '권리금(원)', '관리비(원)', 
        '평단가', '위치'
    ]
    st.dataframe(table_df, use_container_width=True)

    st.markdown("---")

    # --- 상세 분석 및 이미지 갤러리 ---
    st.subheader("🔎 매물 상세 분석 및 이미지")
    
    if not filtered_df.empty:
        selected_title = st.selectbox("분석할 매물을 선택하세요", filtered_df['title'].unique())
        item = filtered_df[filtered_df['title'] == selected_title].iloc[0]
        
        detail_col1, detail_col2 = st.columns([1, 1])
        
        with detail_col1:
            st.write(f"### {item['title']}")
            
            # 투자 지표 요약
            st.info(f"""
            **💰 투자 분석**
            - **초기 투자금 (보고+권리):** {format_won(item['total_investment'])}
            - **예상 월 수익률:** {item['roi']:.2f}% (연간 기준)
            - **투자 회수 기간:** {item['payback_period']:.1f}년
            """)
            
            # 지도 시각화 (좌표 정보가 없으므로 강남역 중심 더미 좌표 활용 - 실제 서비스 시 Geocoding 필요)
            st.write("**📍 위치 정보 (500m 반경)**")
            # 임시 좌표 (강남역 부근)
            lat, lon = 37.4980, 127.0276
            m = folium.Map(location=[lat, lon], zoom_start=15)
            folium.Marker([lat, lon], popup=item['title'], icon=folium.Icon(color='red')).add_to(m)
            folium.Circle([lat, lon], radius=500, color='blue', fill=True, opacity=0.1).add_to(m)
            folium_static(m)

        with detail_col2:
            st.write("#### 📸 이미지 갤러리")
            if item['smallPhotoUrls']:
                # 썸네일 표시
                idx = st.slider("이미지 선택", 0, len(item['smallPhotoUrls'])-1, 0)
                try:
                    img_url = item['originPhotoUrls'][idx]
                    response = requests.get(img_url)
                    img = Image.open(BytesIO(response.content))
                    st.image(img, use_container_width=True, caption=f"{idx+1}/{len(item['smallPhotoUrls'])}")
                except Exception as e:
                    st.warning("이미지를 불러올 수 없습니다.")
            else:
                st.write("등록된 이미지가 없습니다.")

    else:
        st.warning("필터링된 매물이 없습니다.")

if __name__ == "__main__":
    main()
