#!/usr/bin/env python3
"""보조금24(gov24) API → 정규화 programs.json.
사용: GOV24_KEY 환경변수 필수. 출력: public/data/programs.json
GitHub Action(주 1회)이 실행 → 결과를 CDN(appintoss-assets/minsaeng-data)로 커밋.
⛔ 인증키 하드코딩 금지 — 환경변수/시크릿만."""
import urllib.request, urllib.parse, json, os, sys, datetime

KEY = os.environ.get("GOV24_KEY", "")
if not KEY:
    print("ERROR: GOV24_KEY 환경변수 없음", file=sys.stderr); sys.exit(1)
BASE = "https://api.odcloud.kr/api/gov24/v3"
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "data", "programs.json")

# 시도 부분문자열 매칭 (긴 것부터 — 충청남도가 충남보다 먼저 매칭되도록)
SIDO_MATCH = [("서울","서울"),("부산","부산"),("대구","대구"),("인천","인천"),("광주","광주"),("대전","대전"),("울산","울산"),("세종","세종"),("경기","경기"),("강원","강원"),("충청북도","충북"),("충북","충북"),("충청남도","충남"),("충남","충남"),("전북","전북"),("전라북도","전북"),("전라남도","전남"),("전남","전남"),("경상북도","경북"),("경북","경북"),("경상남도","경남"),("경남","경남"),("제주","제주")]
SIDO_SLUG = {"전국":"nationwide","서울":"seoul","부산":"busan","대구":"daegu","인천":"incheon","광주":"gwangju","대전":"daejeon","울산":"ulsan","세종":"sejong","경기":"gyeonggi","강원":"gangwon","충북":"chungbuk","충남":"chungnam","전북":"jeonbuk","전남":"jeonnam","경북":"gyeongbuk","경남":"gyeongnam","제주":"jeju"}
SIDO_ORDER = ["서울","경기","인천","부산","대구","광주","대전","울산","세종","강원","충북","충남","전북","전남","경북","경남","제주"]

def fetch_all(ep):
    out=[]; page=1
    while True:
        p={"serviceKey":KEY,"page":page,"perPage":1000}
        u=BASE+"/"+ep+"?"+urllib.parse.urlencode(p)
        d=json.load(urllib.request.urlopen(u,timeout=60))
        rows=d.get("data",[])
        if not rows: break
        out+=rows; page+=1
        if page>30: break
    return out

def region(agency, atype):
    if atype and "중앙" in atype: return ("전국","")
    if not agency: return ("전국","")
    for kw,sido in SIDO_MATCH:
        if kw in agency:
            parts=agency.split()
            sgg=""
            if len(parts)>1 and (parts[1].endswith("구") or parts[1].endswith("군") or parts[1].endswith("시")):
                sgg=parts[1]
            return (sido, sgg)
    return ("전국","")   # 시도 미포함 기관(공사·재단 등) = 전국

def truthy(v): return v=="Y" or v is True
def targets(c):
    t=[]
    if not c: return t
    spec_free=truthy(c.get("JA0322")); hh_free=truthy(c.get("JA0410"))
    if truthy(c.get("JA0302")) or truthy(c.get("JA0303")): t.append("출산·양육")
    if not spec_free:
        if truthy(c.get("JA0328")): t.append("장애인")
        if truthy(c.get("JA0329")): t.append("국가유공자")
        if truthy(c.get("JA0401")): t.append("다문화")
        if truthy(c.get("JA0403")): t.append("한부모·조손")
        if truthy(c.get("JA0404")): t.append("1인가구")
    if not hh_free:
        if truthy(c.get("JA0411")): t.append("다자녀")
        if truthy(c.get("JA0412")): t.append("무주택")
    if truthy(c.get("JA0327")): t.append("구직자")
    inc=[truthy(c.get(k)) for k in ["JA0201","JA0202","JA0203","JA0204","JA0205"]]
    if any(inc) and not all(inc) and (inc[0] or inc[1]): t.append("저소득·취약계층")
    a0,a1=c.get("JA0110"),c.get("JA0111")
    try:
        if a1 is not None and 19<=int(a1)<=39 and (a0 is None or int(a0)<=34): t.append("청년")
    except: pass
    try:
        if a0 is not None and int(a0)>=60: t.append("어르신")
    except: pass
    return sorted(set(t))
def income(c):
    m=[("JA0201","중위 0~50%"),("JA0202","중위 51~75%"),("JA0203","중위 76~100%"),("JA0204","중위 101~200%"),("JA0205","중위 200%+")]
    ys=[l for k,l in m if c and truthy(c.get(k))]
    return [] if len(ys)==5 else ys
def status_of(s):
    s=(s or "").strip()
    if not s or "상시" in s or "없음" in s or "불필요" in s or "없이" in s: return "상시"
    return "확인필요"

def num(v):
    try: return int(v)
    except: return None

def main():
    svc=fetch_all("serviceList"); cond={c.get("서비스ID"):c for c in fetch_all("supportConditions")}
    bysido={}
    for s in svc:
        sid=s.get("서비스ID"); c=cond.get(sid)
        sido,sgg=region(s.get("소관기관명"), s.get("소관기관유형"))
        p={"id":sid,"name":s.get("서비스명"),"agency":s.get("소관기관명"),
            "sgg":sgg,"category":s.get("서비스분야"),"target":targets(c),
            "ageMin":num(c.get("JA0110")) if c else None,"ageMax":num(c.get("JA0111")) if c else None,
            "income":income(c),"status":status_of(s.get("신청기한")),"period":s.get("신청기한"),
            "url":s.get("상세조회URL"),"summary":(s.get("서비스목적요약") or "")[:140],"source":"gov24"}
        bysido.setdefault(sido,[]).append(p)
    outdir=os.environ.get("OUTDIR") or os.path.join(os.path.dirname(__file__),"..","public","data")
    os.makedirs(outdir,exist_ok=True)
    today=datetime.date.today().isoformat(); manifest={"updated":today,"total":len(svc),"regions":{}}
    for sido,items in bysido.items():
        slug=SIDO_SLUG.get(sido)
        if not slug: continue
        fn=f"programs-{slug}.json"
        json.dump({"sido":sido,"updated":today,"count":len(items),"programs":items},
                  open(os.path.join(outdir,fn),"w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
        manifest["regions"][sido]={"slug":slug,"file":fn,"count":len(items)}
    json.dump(manifest,open(os.path.join(outdir,"manifest.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    try: os.remove(OUT)
    except: pass
    print("regions:", {k:v["count"] for k,v in sorted(manifest["regions"].items(), key=lambda x:-x[1]["count"])})

if __name__=="__main__": main()
