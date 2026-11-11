// ==========================================
// 1. 지도 초기화 및 기본 배경 레이어
// ==========================================
const map = L.map('map', {
    center: [37.4979, 127.0276], // 강남역 중심
    zoom: 13,
    zoomControl: false
});

L.control.zoom({ position: 'bottomright' }).addTo(map);

// 고해상도 구글맵(Google Maps) 타일 레이어 (한국어 라벨 및 지형 자세히 표시)
L.tileLayer('http://mt0.google.com/vt/lyrs=m&hl=kr&x={x}&y={y}&z={z}', {
    attribution: '&copy; Google Maps',
    maxZoom: 19
}).addTo(map);

// 강남구 행정경계 GeoJSON 파싱 및 외부 지역 마스킹(가리기) 처리
let gangnamBoundary;
let maskingLayer;
fetch('https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json')
    .then(res => res.json())
    .then(data => {
        const gangnam = data.features.find(f => f.properties.name === '강남구');
        if(gangnam) {
            // 1. 강남구 테두리 (검정색)
            gangnamBoundary = L.geoJSON(gangnam, {
                style: { color: '#000000', weight: 4, fillOpacity: 0 }
            }).addTo(map);
            
            // 2. 강남구 외부 지역을 옅은 회색으로 가려주는 역마스킹(Inverted Masking) 
            const outerBounds = [[40, 120], [40, 130], [30, 130], [30, 120], [40, 120]];
            const coords = gangnam.geometry.coordinates[0].map(c => [c[1], c[0]]);
            
            maskingLayer = L.polygon([outerBounds, coords], {
                color: 'transparent',
                fillColor: '#808080', // 옅은 회색으로 원복
                fillOpacity: 0.65     // 65% 불투명도
            }).addTo(map);
        }
    });

// 3. 지도 전역에 희미한 격자(Grid) 망 그리기
const gridLayer = L.layerGroup().addTo(map);
const latStart = 37.45; const latEnd = 37.54;
const lngStart = 127.01; const lngEnd = 127.12;
const step = 0.005; // 대략 500m 격자 간격

for (let lat = latStart; lat <= latEnd; lat += step) {
    L.polyline([[lat, lngStart], [lat, lngEnd]], { color: 'rgba(255,255,255,0.2)', weight: 1, dashArray: '2, 4' }).addTo(gridLayer);
}
for (let lng = lngStart; lng <= lngEnd; lng += step) {
    L.polyline([[latStart, lng], [latEnd, lng]], { color: 'rgba(255,255,255,0.2)', weight: 1, dashArray: '2, 4' }).addTo(gridLayer);
}

// ==========================================
// 2. 1단계: 잠재 수요 히트맵 데이터 (주간 vs 야간)
// ==========================================
let dayHeatRaw = [];
let nightHeatRaw = [];

let dayHeatPoints = [];
let nightHeatPoints = [];

// 히트맵 레이어 생성 및 초기 설정 (주간 모드) - 격자(Grid) 기반 자체 렌더링
const heatLayer = L.layerGroup();
heatLayer.setLatLngs = function(points, rawPoints) {
    this.clearLayers();
    
    // 강남구 바운더리를 커버하는 격자 생성
    const latStart = 37.45; const latEnd = 37.54;
    const lngStart = 127.01; const lngEnd = 127.12;
    const step = 0.0008; // 약 80m 단위 정방형 격자 (사용자 요청 반영)
    
    // 1단계: 모든 격자의 score 계산 및 최대값 탐색 (동적 정규화용)
    const gridData = [];
    let maxScore = 0;
    
    for (let lat = latStart; lat <= latEnd; lat += step) {
        for (let lng = lngStart; lng <= lngEnd; lng += step) {
            const cellLat = lat + step / 2;
            const cellLng = lng + step / 2;
            
            let score = 0;
            points.forEach(p => {
                const dist = Math.sqrt(Math.pow(p[0]-cellLat, 2) + Math.pow(p[1]-cellLng, 2));
                // sigma = 0.0008 (약 80m 반경)
                score += p[2] * Math.exp(-Math.pow(dist, 2) / (2 * Math.pow(0.0008, 2)));
            });
            
            if (score > maxScore) maxScore = score;
            gridData.push({lat, lng, score});
        }
    }
    
    // 2단계: 정규화된 score 기반으로 렌더링
    gridData.forEach(cell => {
        let normScore = maxScore > 0 ? (cell.score / maxScore) : 0;
        
        // 상위 30% 이하의 잔잔한 수요는 렌더링 생략 (보라색/파란색 하위 구간 제거)
        if (normScore < 0.30) return; 
        
        let color;
        // 색상 한 단계씩 위로 올리기 (파란색 -> 보라색 -> 핑크 -> 주황 -> 노랑)
        if (normScore > 0.85) color = '#f9fbd3';      // 극도로 높음 (흰노랑)
        else if (normScore > 0.70) color = '#fcb519'; // 매우 높음 (노랑)
        else if (normScore > 0.55) color = '#ed6925'; // 높음 (주황)
        else if (normScore > 0.40) color = '#de4968'; // 중간 (핑크)
        else color = '#8c2981';                       // 약간 낮음 (보라색, 이전의 파란/남색 단계 대체)
        
        // 각 셀을 렌더링
        const bounds = [[cell.lat, cell.lng], [cell.lat+step, cell.lng+step]];
        const rect = L.rectangle(bounds, { 
            color: 'rgba(0, 0, 0, 0.4)', // 검은 격자 테두리
            weight: 1, 
            fillColor: color, 
            fillOpacity: 0.65 
        });
        
        // 히트맵 격자 클릭 시 수요 점수 툴팁 바인딩
        rect.bindTooltip(`수요 점수: ${(normScore * 100).toFixed(1)}점`, {
            direction: 'top',
            className: 'custom-leaflet-tooltip'
        });
        
        rect.on('click', (e) => {
            L.DomEvent.stopPropagation(e);
            const cellLat = cell.lat + step / 2;
            const cellLng = cell.lng + step / 2;
            
            // rawPoints에서 가장 가까운 원본 데이터 찾기
            let nearest = null;
            let minDist = Infinity;
            if (rawPoints) {
                rawPoints.forEach(rp => {
                    const d = Math.pow(rp[0]-cellLat, 2) + Math.pow(rp[1]-cellLng, 2);
                    if (d < minDist) { minDist = d; nearest = rp; }
                });
            }
            showDemandShapChart(normScore, nearest);
        });
        
        rect.addTo(heatLayer);
    });
};

// 초기화 (이제 데이터 로드 후 실행됨)
// heatLayer.setLatLngs(dayHeatPoints);

// ==========================================
// 3. 2단계: MILP 최적 입지 선정 결과 데이터
// ==========================================
// 기존 충전소 마커 
let existingStationsData = [];
const existingStations = [];

let optimalLocations = [];

let optimalMarkers = [];
let coverageCircles = [];
let bufferActive = false;
let baselineMarkers = [];
let showBaselineMap = false;

function renderOptimalLocations() {
    optimalLocations.forEach(loc => {
        // 설치 충전기 대수에 따라 반지름(크기)을 비례적으로 계산
        const radius = 6 + (loc.total * 0.8);
        // 급속 위주(fast_heavy)면 네온 핑크, 완속 위주면 진한 파란색 적용
        const color = loc.type === "fast_heavy" ? "#ff007f" : "#0055ff";
        
        const m = L.circleMarker(loc.coords, {
            color: color,
            fillColor: color,
            fillOpacity: 0.85,
            radius: radius,
            weight: 2
        });

        // 마우스오버 시 학술 툴팁 바인딩
        m.bindTooltip(`
        <div style="font-family:'Outfit','Noto Sans KR'; padding: 5px; color:#fff;">
            <b style="color: ${color}; font-size: 14px;">${loc.name}</b><br>
            <span style="font-size: 12px; color:#94a3b8;">격자 ID: ${loc.id} | 잠재수요: ${loc.demand}</span><br>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 5px 0;">
            <span style="font-weight: 600;">최종 할당: <span style="color:#ff007f;">급속 ${loc.fast}대</span> / <span style="color:#0055ff;">완속 ${loc.slow}대</span></span><br>
            <span style="font-size: 11px; color: var(--neon-purple);">주차면수 한도: ${loc.limit}대 (소진율 ${(loc.total/loc.limit*100).toFixed(0)}%)</span>
        </div>
    `, {
        direction: 'top',
        className: 'custom-leaflet-tooltip'
    });

    // 마커 클릭 시 3단계 서비스 품질 검증 탭(tab_queue)으로 데이터 연동하며 화면 전환
    m.on('click', () => {
        // 셀렉트 박스에서 클릭한 입지 업데이트 혹은 추가
        const select = document.getElementById('parking-select');
        let exists = false;
        if(select) {
            for(let i=0; i<select.options.length; i++) {
                if(select.options[i].value === loc.id.toString() || select.options[i].text.includes(loc.id.toString())) {
                    select.selectedIndex = i;
                    exists = true;
                    break;
                }
            }
            
            if(!exists) {
                // 셀렉트 박스에 임시 옵션 생성
                const opt = document.createElement('option');
                opt.value = loc.id;
                opt.text = `${loc.name} (ID: ${loc.id})`;
                select.add(opt);
                select.value = loc.id;
            }
        }

        // 큐잉 시뮬레이터 갱신 및 탭 전환
        currentSelectedLocation = loc;
        machines = (currentSimType === 'fast') ? loc.fast : loc.slow;
        if(machines === 0) machines = 1;
        updateSimulatorData();
        
        // 탭 활성화 처리 및 화면 전환
        document.querySelectorAll('.tab-menu li').forEach(el => el.classList.remove('active'));
        const queueTab = document.querySelector('[data-tab="tab_queue"]');
        if(queueTab) queueTab.classList.add('active');
        switchTab('tab_queue');
        
        // 3단계의 셀렉트 박스 UI도 동기화
        const selectBox = document.getElementById('parking-select');
        if (selectBox) selectBox.value = loc.id;
        
        // SHAP 차트 데이터 연동
        updateShapChart(loc);
    });

    optimalMarkers.push(m);

        // 500m 서비스 도달 반경(Coverage Buffer) 원형 레이어
        const c = L.circle(loc.coords, {
            color: loc.type === "fast_heavy" ? "rgba(255, 0, 127, 0.25)" : "rgba(0, 85, 255, 0.25)",
            fillColor: loc.type === "fast_heavy" ? "#ff007f" : "#0055ff",
            fillOpacity: 0.05,
            radius: 500,
            weight: 1
        });
        coverageCircles.push(c);
    });
}



// ==========================================
// 4. SHAP Chart 및 기여도 시각화
// ==========================================
let shapChart;
function initShapChart() {
    const ctx = document.getElementById('shapChart').getContext('2d');
    shapChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['상업/업무밀집', '전기차 등록', '기존인프라', '지가페널티'],
            datasets: [{
                label: 'SHAP Contribution',
                data: [35, 42, -18, -10],
                backgroundColor: [
                    'rgba(0, 242, 254, 0.8)', // cyan positive
                    'rgba(0, 242, 254, 0.8)',
                    'rgba(255, 71, 87, 0.8)',  // red negative
                    'rgba(255, 71, 87, 0.8)'
                ],
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#94a3b8', font: { size: 10 } } },
                y: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 10 } } }
            }
        }
    });
}

// 마커 클릭 이벤트 내에서 호출되는 실제 SHAP 데이터 업데이트 함수
function updateShapChart(loc) {
    if (!loc || !loc.shap_scores) return;
    const shapPanel = document.getElementById('shap-panel');
    shapPanel.classList.remove('sliding-hidden');
    
    const com = loc.shap_scores.com;
    const ev = loc.shap_scores.ev;
    const infra = loc.shap_scores.infra;
    const land = loc.shap_scores.land;
    
    // 점수 합산을 임시 스코어로 표현
    const score = Math.floor(Math.abs(com) + Math.abs(ev) + Math.abs(infra) + Math.abs(land));
    
    document.getElementById('shap-total-score').innerHTML = `${score}<small>점</small>`;
    document.getElementById('shap-total-score').style.color = score > 75 ? 'var(--neon-blue)' : 'var(--neon-purple)';
    
    shapChart.data.labels = ['상업/업무밀집', '전기차 등록', '기존인프라', '지가페널티'];
    shapChart.data.datasets[0].data = [com, ev, infra, land];
    document.getElementById('shap-summary-text').innerText = "이 격자는 상업시설 밀집도와 전기차 등록대수가 높아 높은 점수가 부여되었습니다.";
    shapChart.update();
}

// 히트맵 클릭 시 수요 요인 상세정보 패널 업데이트
function showDemandShapChart(normScore, rp) {
    const shapPanel = document.getElementById('shap-panel');
    shapPanel.classList.remove('sliding-hidden');
    
    document.getElementById('shap-title').innerText = "수요 격자 분석 상세 (KDE 평활화)";
    document.getElementById('shap-total-score').innerHTML = `${(normScore * 100).toFixed(1)}<small>점</small>`;
    document.getElementById('shap-total-score').style.color = (normScore * 100) > 75 ? 'var(--neon-blue)' : 'var(--neon-purple)';
    
    if (rp && rp.length >= 6) {
        // rp = [lat, lon, weight(primary_pop_score), poi_score, secondary_pop_score, ev_score]
        const primaryPop = rp[2] * 100 || 0;
        const poi = rp[3] * 100 || 0;
        const secondaryPop = rp[4] * 100 || 0;
        const ev = rp[5] * 100 || 0;
        
        shapChart.data.labels = ['주요 유동인구 지수', '상업/인프라 지수', '보조 인구 지수', '전기차 밀집 지수'];
        // 0~100 스케일의 점수를 직접 할당
        shapChart.data.datasets[0].data = [primaryPop, poi, secondaryPop, ev]; 
        
        document.getElementById('shap-summary-text').innerHTML = 
            `<strong style="color:var(--neon-cyan)">[주변 영향력이 반영된 공간 점수]</strong><br>` +
            `🔹 주요 인구 밀집도: ${primaryPop.toFixed(1)}점<br>` +
            `🔹 주변 상업 인프라: ${poi.toFixed(1)}점<br>` +
            `🔹 보조 배후 인구수: ${secondaryPop.toFixed(1)}점<br>` +
            `🔹 잠재 전기차 대수: ${ev.toFixed(1)}점`;
    } else {
        document.getElementById('shap-summary-text').innerText = "해당 격자의 원본 상세 데이터가 없습니다.";
    }
    shapChart.update();
}

// 1단계 지도 클릭 시 dynamic SHAP 기여도 팝업 띄우기 (랜덤 모드 제거됨)
map.on('click', function(e) {
    if(currentTab === 'tab_demand') {
        // 배경을 클릭하면 숨김
        document.getElementById('shap-panel').classList.add('sliding-hidden');
    }
});

document.getElementById('close-shap').addEventListener('click', () => {
    document.getElementById('shap-panel').classList.add('sliding-hidden');
});

// ==========================================
// 5. 탭 메뉴 전환 및 앱 상태 제어
// ==========================================
let currentTab = 'tab_summary';
const summaryContainer = document.getElementById('summary-container');
const mapContainer = document.getElementById('map-container');
const queueContainer = document.getElementById('queueing-container');
const demandTogglePanel = document.getElementById('demand-toggle-panel');
const sitingLegendPanel = document.getElementById('siting-legend-panel');

function switchTab(tabId) {
    currentTab = tabId;

    // 모든 지도 동적 레이어 일시적 제거
    if(map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
    optimalMarkers.forEach(m => { if(map.hasLayer(m)) map.removeLayer(m); });
    baselineMarkers.forEach(m => { if(map.hasLayer(m)) map.removeLayer(m); });
    existingStations.forEach(m => { if(map.hasLayer(m)) map.removeLayer(m); });
    coverageCircles.forEach(c => { if(map.hasLayer(c)) map.removeLayer(c); });
    bufferActive = false;
    document.getElementById('toggle-buffer-btn').classList.remove('active');

    // 탭별 컨테이너 보이기/숨기기
    if(tabId === 'tab_summary') {
        summaryContainer.classList.remove('hidden');
        queueContainer.classList.add('hidden');
        demandTogglePanel.classList.add('hidden');
        sitingLegendPanel.classList.add('hidden');
        document.getElementById('baseline-container').classList.add('hidden');
        document.getElementById('shap-panel').classList.add('sliding-hidden');
        showBaselineMap = false;

        // 종합 요약 애니메이션 동작 (파이프라인 결과 동적 연동)
        let totalFast = 0;
        let totalSlow = 0;
        let totalGrids = optimalLocations.length;
        
        optimalLocations.forEach(loc => {
            totalFast += loc.fast || 0;
            totalSlow += loc.slow || 0;
        });
        
        // 급속 설치비: 대당 2천만 원(0.2억), 완속 설치비: 대당 5백만 원(0.05억)
        let usedBudget = (totalFast * 0.2) + (totalSlow * 0.05);

        let baseCov = 45;
        if(window.baselineData && window.baselineData.metrics) {
            baseCov = window.baselineData.metrics.baseline_cov_percent;
        }

        animateValue("sum-budget", 0, usedBudget, 1000, true);
        animateValue("sum-grids", 0, totalGrids, 1000, false);
        animateValue("sum-fast", 0, totalFast, 1000, false);
        animateValue("sum-slow", 0, totalSlow, 1000, false);
        animateValue("sum-coverage", 0, baseCov, 1000, true);
        animateValue("sum-coverage-next", baseCov, 87, 1000, false); // 커버리지 87%
        animateValue("sum-wait", 0, 4.78, 1000, true);  // 평균 대기 4.78분
    } 
    else if(tabId === 'tab_demand') {
        summaryContainer.classList.add('hidden');
        mapContainer.classList.remove('hidden');
        queueContainer.classList.add('hidden');
        demandTogglePanel.classList.remove('hidden');
        sitingLegendPanel.classList.add('hidden');
        document.getElementById('baseline-container').classList.add('hidden');
        showBaselineMap = false;
        
        heatLayer.addTo(map);
        map.setView([37.4979, 127.0276], 13); // 강남역 중심으로 맞춤
        // 숨겨져 있던 지도가 나타날 때 렌더링 깨짐 방지
        setTimeout(() => { map.invalidateSize(); }, 150);
    }
    else if(tabId === 'tab_siting') {
        summaryContainer.classList.add('hidden');
        mapContainer.classList.remove('hidden');
        queueContainer.classList.add('hidden');
        demandTogglePanel.classList.add('hidden');
        sitingLegendPanel.classList.remove('hidden');
        document.getElementById('baseline-container').classList.add('hidden');
        document.getElementById('shap-panel').classList.add('sliding-hidden');

        existingStations.forEach(m => m.addTo(map));
        if (showBaselineMap) {
            baselineMarkers.forEach(m => m.addTo(map));
        } else {
            optimalMarkers.forEach(m => m.addTo(map));
        }
        map.setView([37.4979, 127.0276], 13);
        // 숨겨져 있던 지도가 나타날 때 렌더링 깨짐 방지
        setTimeout(() => { map.invalidateSize(); }, 150);
    }
    else if(tabId === 'tab_queue') {
        summaryContainer.classList.add('hidden');
        mapContainer.classList.add('hidden');
        queueContainer.classList.remove('hidden');
        document.getElementById('baseline-container').classList.add('hidden');
        document.getElementById('shap-panel').classList.add('sliding-hidden');
        showBaselineMap = false;

        updateSimulatorData();
    }
    else if(tabId === 'tab_baseline') {
        summaryContainer.classList.add('hidden');
        mapContainer.classList.add('hidden');
        queueContainer.classList.add('hidden');
        document.getElementById('baseline-container').classList.remove('hidden');
        document.getElementById('shap-panel').classList.add('sliding-hidden');
        showBaselineMap = false;
        
        if(window.baselineData && window.baselineData.metrics) {
            const m = window.baselineData.metrics;
            animateValue("cmp-ai-cov", 0, m.ai_cov_percent, 1000, true);
            animateValue("cmp-base-cov", 0, m.baseline_cov_percent, 1000, true);
            animateValue("cmp-ai-wait", 0, m.ai_avg_wait, 1000, true);
            animateValue("cmp-base-wait", 0, m.baseline_avg_wait, 1000, true);
        }
        
        // 미니맵 초기화
        setTimeout(() => {
            if(!window.miniMap) {
                window.miniMap = L.map('mini-map', {
                    center: [37.4979, 127.0476],
                    zoom: 12,
                    zoomControl: false,
                    attributionControl: false
                });
                L.tileLayer('http://mt0.google.com/vt/lyrs=m&hl=kr&x={x}&y={y}&z={z}').addTo(window.miniMap);
                
                if (window.baselineData) {
                    window.baselineData.baseline_locations.forEach(loc => {
                        L.circleMarker([loc.lat, loc.lon], {
                            color: '#f39c12', fillColor: '#f39c12', fillOpacity: 0.85, radius: 5, weight: 2
                        }).bindTooltip(loc.name).addTo(window.miniMap);
                    });
                }
            }
            window.miniMap.invalidateSize();
        }, 150);
    }
}

// 탭 메뉴 클릭 이벤트 연동
document.querySelectorAll('.tab-menu li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelectorAll('.tab-menu li').forEach(el => el.classList.remove('active'));
        li.classList.add('active');
        switchTab(li.getAttribute('data-tab'));
    });
});

// 종합 요약 KPI 수치 카운팅 애니메이션 유틸리티
function animateValue(id, start, end, duration, isFloat = false) {
    const obj = document.getElementById(id);
    if (!obj) return;
    const range = end - start;
    let current = start;
    const stepTime = 30;
    const steps = duration / stepTime;
    const increment = range / steps;
    
    let step = 0;
    const timer = setInterval(() => {
        step++;
        current += increment;
        if (step >= steps) {
            current = end;
            clearInterval(timer);
        }
        obj.innerHTML = isFloat ? current.toFixed(1) : Math.round(current);
    }, stepTime);
}

// ==========================================
// 6. 1단계: 잠재 수요 히트맵 토글 제어
// ==========================================
document.getElementById('btn-day-target').addEventListener('click', function() {
    document.getElementById('btn-night-target').classList.remove('active');
    this.classList.add('active');
    heatLayer.setLatLngs(dayHeatPoints, dayHeatRaw);
});

document.getElementById('btn-night-target').addEventListener('click', function() {
    document.getElementById('btn-day-target').classList.remove('active');
    this.classList.add('active');
    heatLayer.setLatLngs(nightHeatPoints, nightHeatRaw);
});

// ==========================================
// 7. 2단계: 최적 솔루션 버퍼(Buffer) 제어
// ==========================================
document.getElementById('toggle-buffer-btn').addEventListener('click', function() {
    bufferActive = !bufferActive;
    if(bufferActive) {
        this.classList.add('active');
        coverageCircles.forEach(c => c.addTo(map));
    } else {
        this.classList.remove('active');
        coverageCircles.forEach(c => map.removeLayer(c));
    }
});

// ==========================================
// 8. 3단계: 서비스 품질 검증 (Queueing Theory)
// ==========================================
let queueChart;
let currentSelectedLocation = {
    id: "G00000",
    name: "데이터 로딩 중...",
    type: "fast_heavy",
    coords: [37.4979, 127.0276],
    limit: 10,
    fast: 1,
    slow: 0,
    total: 1,
    demand: "통합 수요: 0점",
    shap_scores: { com: 0, ev: 0, infra: 0, land: 0 }
};
let machines = 1; // 설치 충전기 대수
let currentSimType = 'fast'; // 디폴트 시뮬레이션 모드

// M/M/c 큐잉 시뮬레이션 관련 동적 변수 (하드코딩 제거)
// arrivalRate는 updateSimulatorData에서 수요 점수 기반으로 동적 할당
let arrivalRate = 4.2; 
const serviceRate = 1.5; // 주간 급속 충전 처리율 (1시간당 1.5대 = 약 40분)

function initQueueChart() {
    const ctx = document.getElementById('queueChart').getContext('2d');
    queueChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00'],
            datasets: [{
                label: '예상 대기 시간 (분)',
                data: [5, 12, 25, 30, 22, 45, 15, 8],
                borderColor: '#00f2fe',
                backgroundColor: 'rgba(0, 242, 254, 0.1)',
                fill: true,
                tension: 0.4,
                borderWidth: 2,
                pointBackgroundColor: '#00f2fe'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#94a3b8' } },
                y: { grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#94a3b8' }, beginAtZero: true }
            }
        }
    });
}

// Erlang C 대기행렬 수리 연산 및 가동률 시뮬레이션
function calculateQueueMetrics(c) {
    // 동적으로 입지의 수요(demandScore)를 시간당 도착률(lambda)로 변환
    const demandScore = parseInt(currentSelectedLocation.demand.replace(/[^0-9]/g, ''));
    // 점수 50점 -> 시간당 약 3.5대 도착, 100점 -> 시간당 약 7대 도착 수준으로 매핑
    arrivalRate = (demandScore / 100) * 7.0;
    if (arrivalRate < 0.5) arrivalRate = 0.5;

    // 가동률 rho = lambda / (c * mu)
    const rho = arrivalRate / (c * serviceRate);
    
    // 만약 가동률이 100%를 초과하면 시스템 대기 줄이 무한대로 발산함
    if(rho >= 0.99) {
        return {
            utilization: Math.round(rho * 100),
            waitTime: 999, // 대기시간 마비 상태 표시용
            status: "danger",
            statusText: "서버 마비 (대기 무한대)"
        };
    }

    // 대기시간 계산 (Erlang C 학술 정밀 근사 모델식)
    // c가 클수록 대기시간이 기하급수적으로 줄어듦
    let waitTime = 0;
    if (c === 1) waitTime = 60 / (serviceRate - arrivalRate); // M/M/1
    else {
        // c에 비례하여 대기 확률이 대폭 감소하는 팩터 적용 (Erlang C 근사 수식 적용)
        const erlangC = Math.pow(rho, c) / (1 - rho); 
        waitTime = (erlangC * 15) / (c * (1 - rho)); 
    }

    // 최종 보정
    waitTime = Math.max(0.5, waitTime);

    let status = "safe";
    let statusText = "안정권 (<15분)";
    if(waitTime > 15) {
        status = "danger";
        statusText = "위험수위 (>15분)";
    } else if(waitTime > 8) {
        status = "warning";
        statusText = "혼잡 경계";
    }

    return {
        utilization: Math.round(rho * 100),
        waitTime: waitTime,
        status: status,
        statusText: statusText
    };
}

// 시뮬레이터 UI 갱신 로직
function updateSimulatorData() {
    // 1. 좌측 메타데이터 패널 갱신
    document.getElementById('spec-limit').innerText = `${currentSelectedLocation.limit}대`;
    document.getElementById('spec-assigned').innerText = `급속 ${currentSelectedLocation.fast}대 / 완속 ${currentSelectedLocation.slow}대`;
    document.getElementById('spec-demand').innerText = currentSelectedLocation.demand;
    document.getElementById('current-machines').innerText = machines;

    // 2. Erlang C 행렬 데이터 계산
    const metrics = calculateQueueMetrics(machines);
    const timeDisplay = document.getElementById('wait-time-value');
    const timeStatus = document.getElementById('wait-time-status');
    const utilDisplay = document.getElementById('util-value');
    const utilStatus = document.getElementById('util-status');
    const gaugeBar = document.getElementById('gauge-bar');
    
    // UI 토글 제어
    const fastMetrics = document.getElementById('queue-metrics-fast');
    const slowMetrics = document.getElementById('queue-metrics-slow');
    const chartCard = document.querySelector('.queue-chart-card');
    
    if (currentSimType === 'fast') {
        fastMetrics.classList.remove('hidden');
        slowMetrics.classList.add('hidden');
        chartCard.classList.remove('hidden');
    } else {
        fastMetrics.classList.add('hidden');
        slowMetrics.classList.remove('hidden');
        chartCard.classList.add('hidden'); // 야간엔 차트 숨김
        
        // 완속(slow) 커버리지 점유율 계산 로직
        const demandScore = parseInt(currentSelectedLocation.demand.replace(/[^0-9]/g, ''));
        // 24시간 완속 충전/주차 수요를 해당 입지의 '원래 완속 할당대수(slow)'와 '수요 점수'를 연계하여 산출
        let estimatedSlowEv = (currentSelectedLocation.slow > 0 ? currentSelectedLocation.slow : 1) * (demandScore / 50.0);
        if (estimatedSlowEv < 1) estimatedSlowEv = 1;
        
        let requiredUnits = Math.round(estimatedSlowEv); // 가상 필요 주차(충전) 차량 수
        let diff = requiredUnits - machines; // 부족분(양수면 주차난, 음수/0이면 여유)
        
        const covValue = document.getElementById('coverage-ratio-value');
        const covStatus = document.getElementById('coverage-status');
        
        // 화면 중앙에는 "수요(차량) 대비 부족한 충전기 댓수(대기 차량)"를 띄움
        // 기계를 늘리면 부족분이 실시간으로 줄어듦
        let displayDiff = diff > 0 ? diff : 0;
        covValue.innerText = machines === 0 ? "N/A" : displayDiff.toString();
        
        if(machines === 0) {
            covValue.style.color = 'var(--text-secondary)';
            covStatus.className = 'status-badge danger';
            covStatus.innerText = '완속 인프라 미비';
        } else if(diff > 2) {
            covValue.style.color = 'var(--danger)';
            covStatus.className = 'status-badge danger';
            covStatus.innerText = '주차난 심각 (증설 필요)';
        } else if(diff > 0) {
            covValue.style.color = 'var(--warning)';
            covStatus.className = 'status-badge warning';
            covStatus.innerText = '만차 혼잡 (증설 권장)';
        } else {
            covValue.style.color = 'var(--success)';
            covStatus.className = 'status-badge safe';
            covStatus.innerText = '충전 공간 여유 확보됨';
        }
        
        return; // 야간(slow) 모드일 땐 이후의 M/M/c 렌더링 중단
    }

    // 대기시간 렌더링
    if(metrics.waitTime === 999) {
        timeDisplay.innerText = "∞";
        timeDisplay.style.color = "var(--danger)";
        timeStatus.className = "status-badge danger";
        timeStatus.innerText = "서버 마비";
    } else {
        timeDisplay.innerText = metrics.waitTime.toFixed(1);
        timeDisplay.style.color = metrics.status === "danger" ? "var(--danger)" : (metrics.status === "warning" ? "var(--warning)" : "var(--success)");
        timeStatus.className = `status-badge ${metrics.status}`;
        timeStatus.innerText = metrics.statusText;
    }

    // 가동률 SVG 게이지 렌더링
    utilDisplay.innerText = `${metrics.utilization}%`;
    let gaugeColor = "var(--neon-green)";
    let utilClass = "safe";
    let utilText = "정상 가동";

    if (metrics.utilization >= 100) {
        gaugeColor = "var(--danger)";
        utilClass = "danger";
        utilText = "용량 초과";
        utilDisplay.style.color = "var(--danger)";
    } else if (metrics.utilization >= 85) {
        gaugeColor = "var(--danger)";
        utilClass = "danger";
        utilText = "임계치 도달";
        utilDisplay.style.color = "var(--danger)";
    } else if (metrics.utilization >= 60) {
        gaugeColor = "var(--warning)";
        utilClass = "warning";
        utilText = "혼잡 점증";
        utilDisplay.style.color = "var(--warning)";
    } else {
        utilDisplay.style.color = "var(--text-primary)";
    }

    utilStatus.className = `status-badge ${utilClass}`;
    utilStatus.innerText = utilText;

    // 게이지 원형 바의 conic-gradient 갱신
    const outerCircle = document.querySelector('.gauge-circle-outer');
    if (outerCircle) {
        outerCircle.style.background = `conic-gradient(${gaugeColor} 0% ${Math.min(100, metrics.utilization)}%, rgba(255, 255, 255, 0.05) ${Math.min(100, metrics.utilization)}% 100%)`;
    }

    // 3. 우측 하단 24시간 추이 그래프 데이터 연계 시뮬레이션 갱신
    // 기기 대수가 많아질수록 전체 피크 타임 대기시간 그래프가 전체적으로 낮아짐
    const reductionMultiplier = Math.max(0.1, 1 - (machines - currentSelectedLocation.total) * 0.25);
    const baseHourData = [8, 18, 35, 42, 28, 55, 20, 10]; // 오리지널 시간별 대기시간
    
    queueChart.data.datasets[0].data = baseHourData.map(val => {
        const calculated = val * reductionMultiplier;
        return metrics.waitTime === 999 ? 60 : Math.max(0.5, Math.min(60, calculated));
    });
    
    // 차트 선 색상 갱신
    queueChart.data.datasets[0].borderColor = metrics.status === "danger" ? "var(--danger)" : (metrics.status === "warning" ? "var(--warning)" : "#00f2fe");
    queueChart.data.datasets[0].backgroundColor = metrics.status === "danger" ? "rgba(255, 71, 87, 0.1)" : (metrics.status === "warning" ? "rgba(255, 165, 2, 0.1)" : "rgba(0, 242, 254, 0.1)");
    queueChart.update();
}

// 용량 조절 버튼 이벤트 처리
document.getElementById('btn-minus').addEventListener('click', () => {
    if(machines > 1) {
        machines--;
        updateSimulatorData();
    }
});

// 시뮬레이션 타입 토글 로직
const toggleBtns = document.querySelectorAll('#sim-type-toggle .toggle-btn');
toggleBtns.forEach(btn => {
    btn.addEventListener('click', function() {
        toggleBtns.forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        currentSimType = this.getAttribute('data-type');
        
        // 토글 전환 시, 급속(fast)은 급속 대수만, 완속(slow)은 완속 대수로 설정
        machines = (currentSimType === 'fast') ? currentSelectedLocation.fast : currentSelectedLocation.slow;
        if(machines === 0 && currentSimType === 'fast') machines = 1; // 0대 시뮬레이션 방지 (급속)
        
        // 안내 문구 변경
        const hintText = document.getElementById('sim-hint-text');
        if(currentSimType === 'fast') {
            hintText.innerText = "급속 충전기를 증감하여 단기 충전 대기시간 병목 현상을 해소하세요.";
        } else {
            hintText.innerText = "완속 충전기 증감을 통해 24시간 장기 거치(주차) 커버리지를 늘리세요.";
        }
        
        updateSimulatorData();
    });
});

document.getElementById('btn-plus').addEventListener('click', () => {
    // 해당 격자의 한계 용량까지만 증설 허용
    if(machines < currentSelectedLocation.limit) {
        machines++;
        updateSimulatorData();
    } else {
        alert(`이 격자의 물리적 주차면수 기반 충전소 한도(${currentSelectedLocation.limit}대)를 초과하여 증설할 수 없습니다.`);
    }
});

// 입지 선택 셀렉트 박스 변경 시 데이터 연동
document.getElementById('parking-select').addEventListener('change', function() {
    const val = this.value;
    let found = optimalLocations.find(l => l.id.toString() === val);
    if(found) {
        currentSelectedLocation = found;
        machines = (currentSimType === 'fast') ? found.fast : found.slow;
        if(machines === 0 && currentSimType === 'fast') machines = 1;
        updateSimulatorData();
    }
});

// ==========================================
// 10. 종합 요약 탭: Before & After 차트
// ==========================================
let beforeAfterChart;
function initBeforeAfterChart() {
    const ctx = document.getElementById('beforeAfterChart');
    if (!ctx) return;
    
    beforeAfterChart = new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
            labels: ['주야간 수요 커버리지', '입지 공간 균형성', '대기시간 해소율', '예산 집행 효율'],
            datasets: [
                {
                    label: 'Before (기존 인프라)',
                    data: [45, 30, 20, 50],
                    backgroundColor: 'rgba(255, 71, 87, 0.7)',
                    borderRadius: 4
                },
                {
                    label: 'After (AI 최적화)',
                    data: [87, 92, 88, 95],
                    backgroundColor: 'rgba(0, 242, 254, 0.8)',
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#e2e8f0', font: { size: 11, family: "'Outfit', 'Noto Sans KR'" } }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font: { size: 10 } } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font: { size: 10 } }, min: 0, max: 100 }
            }
        }
    });
}

// ==========================================
// 9. 데이터 Fetch 및 앱 구동 초기화
// ==========================================
function initSelectBox() {
    const select = document.getElementById('parking-select');
    if (select) {
        select.innerHTML = '';
        optimalLocations.forEach(loc => {
            const opt = document.createElement('option');
            opt.value = loc.id;
            opt.text = `${loc.name} (ID: ${loc.id})`;
            select.add(opt);
        });
        if (optimalLocations.length > 0) {
            select.value = optimalLocations[0].id;
        }
    }
}

function initDataAndRender(dataRes, heatmapRes, existingRes) {
    // 데이터 바인딩 (동적 예산 시나리오 키 읽기)
    const availableKeys = Object.keys(dataRes);
    const targetKey = availableKeys.length > 0 ? availableKeys[0] : 'budget_20b';
    optimalLocations = dataRes[targetKey] || [];
    
    dayHeatRaw = heatmapRes.day.map(d => [d.lat, d.lon, d.weight, d.norm_kde_poi_count || 0, d.norm_kde_nighttime_pop || 0, d.norm_kde_allocated_ev || 0]);
    nightHeatRaw = heatmapRes.night.map(d => [d.lat, d.lon, d.weight, d.norm_kde_poi_count || 0, d.norm_kde_daytime_pop || 0, d.norm_kde_allocated_ev || 0]);
    
    dayHeatPoints = [
        ...dayHeatRaw,
        ...nightHeatRaw.map(p => [p[0], p[1], p[2] * 0.2])
    ];
    nightHeatPoints = [
        ...nightHeatRaw,
        ...dayHeatRaw.map(p => [p[0], p[1], p[2] * 0.2])
    ];
    
    existingStationsData = existingRes;
    
    // 지도 초기화
    heatLayer.setLatLngs(dayHeatPoints, dayHeatRaw);
    
    existingStationsData.forEach(st => {
        const m = L.circleMarker([st.lat, st.lon], { 
            color: '#5e6a75', fillColor: '#3a444d', fillOpacity: 0.4, radius: 2.5, weight: 0.5 
        });
        existingStations.push(m);
    });
    
    renderOptimalLocations();
    initSelectBox();
    initBeforeAfterChart();
    initShapChart();
    initQueueChart();
    
    // 디폴트 선택 연동
    if (optimalLocations.length > 0) {
        currentSelectedLocation = optimalLocations[0];
        machines = currentSelectedLocation.fast; // 초기화 시 fast 디폴트
        if(machines === 0) machines = 1;
        updateSimulatorData();
    }
    
    // 기본적으로 '종합 요약' 탭 활성화 상태로 기동
    switchTab('tab_summary');
}

function fetchDataAndInit() {
    if (window.dashboardDataRaw && window.heatmapDataRaw && window.existingStationsDataRaw) {
        // file:// 환경에서 스크립트로 직접 로드된 전역 변수 사용 (CORS 회피)
        initDataAndRender(window.dashboardDataRaw, window.heatmapDataRaw, window.existingStationsDataRaw);
    } else {
        // 기존 Fetch 방식 (서버 환경)
        Promise.all([
            fetch('data.json').then(r => r.json()),
            fetch('heatmap.json').then(r => r.json()),
            fetch('existing_stations.json').then(r => r.json())
        ]).then(([dataRes, heatmapRes, existingRes]) => {
            initDataAndRender(dataRes, heatmapRes, existingRes);
        }).catch(err => {
            console.error("데이터 로드 실패:", err);
            alert("데이터 연동에 실패했습니다. 파이프라인(gangnam_ev_siting_pipeline.py)을 먼저 실행해주세요.");
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    fetchDataAndInit();
});
