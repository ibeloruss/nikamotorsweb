import os,re,json,math,xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse,parse_qs,quote_plus
import requests
from flask import Flask,request,jsonify,render_template_string

app=Flask(__name__)
BASE="https://api.xapikorea.com/v1"
MAX_PHOTOS=10
HTML="""<!doctype html><html lang=ru><meta name=viewport content="width=device-width,initial-scale=1"><title>NIKA MOTORS</title>
<style>body{font:16px system-ui;max-width:850px;margin:22px auto;padding:0 15px;background:#111;color:#eee}input,button{font:inherit;width:100%;box-sizing:border-box;padding:13px;margin:7px 0;border-radius:9px;border:1px solid #555;background:#222;color:#eee}button{background:#b71c1c;color:white;border:0;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere}.photos img{width:145px;height:100px;object-fit:cover;margin:4px}a{color:#9ecbff}.item{background:#1d1d1d;padding:10px;border-radius:8px;margin:6px 0}.characteristic{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.edit-btn{width:auto;padding:7px 12px;margin:0;background:#333;border:1px solid #666;border-radius:7px;font-size:14px}.inline-edit{width:auto;max-width:100%;margin:0;padding:8px;background:#fff;color:#111;border-radius:7px}</style>
<h2>🚘 NIKA MOTORS · Encar Parser</h2><p>Вставь ссылку Encar или ID. Максимум 10 фотографий.</p>
<form method=post action=/auto-publish><input name=car placeholder="Вставь ссылку Encar или ID" value="{{car}}" required><button>Автоматически рассчитать и отправить в Telegram</button></form><p>Система сама загрузит курсы валют, рассчитает предварительную цену до Москвы и отправит объявление, если обязательные данные подтверждены.</p>
{% if data %}<div class=item><b>Статус:</b> {{data.status}} · <b>Фото:</b> {{data.photos|length}} из 10</div>
{% if data.title %}<h3>{{data.title}}</h3>{% endif %}
{% for label,key in [('Марка','brand'),('Модель','model'),('Комплектация Encar','trim'),('Дата производства','production_date'),('Пробег, км','mileage_km'),('Цена, KRW','price_krw'),('Двигатель, см³','engine_cc'),('Мощность, л.с.','power_hp'),('Мощность, кВт','power_kw'),('Топливо','fuel'),('КПП','transmission'),('Привод','drive'),('VIN','vin')] %}
{% if key in ['fuel','transmission'] %}<div class="item characteristic"><div><b>{{label}}:</b> <span id="{{key}}Value">{{data[key] or 'Не указано'}}</span></div><button type="button" class="edit-btn" onclick="toggleEdit('{{key}}')">Изменить</button><select class="inline-edit" id="{{key}}Edit" name="{{'manual_fuel' if key == 'fuel' else 'manual_transmission'}}" form="calcForm" {% if not data[key] %}required{% endif %} hidden><option value="">Выбрать</option>{% if key == 'fuel' %}{% for v in ['Гибрид','Бензин','Дизель'] %}<option value="{{v}}" {% if data[key] == v %}selected{% endif %}>{{v}}</option>{% endfor %}{% else %}{% for v in ['Автомат','Механика','Робот','Вариатор'] %}<option value="{{v}}" {% if data[key] == v %}selected{% endif %}>{{v}}</option>{% endfor %}{% endif %}</select></div>{% elif data[key] is not none %}<div class=item><b>{{label}}:</b> {{data[key]}}</div>{% endif %}
{% endfor %}
<p><b>Не найдены:</b> {{data.missing_fields|join(', ')}}</p>
{% if data.photos %}<div class=photos>{% for p in data.photos %}<a href="{{p}}" target=_blank><img src="{{p}}" loading=lazy></a>{% endfor %}</div>{% else %}<b>Фотографии не получены — не публиковать.</b>{% endif %}
<hr><h3>Расчёт и публикация</h3>
<form id="calcForm" method=post action=/calculate>
<input type=hidden name=car_id value="{{data.id}}">
<input type=hidden name=rate value="{{calc.rate if calc else default_rate}}">
<input type=hidden name=eur_rate value="{{calc.eur_rate if calc else default_eur_rate}}">
<input type=hidden name=customs_adjustment value="{{calc.customs_adjustment if calc else 0}}">
<input type=hidden name=kr_extra value="{{calc.kr_extra if calc else 1740000}}">
<input type=hidden name=ru_extra value="{{calc.ru_extra if calc else 450000}}">
{% set exact_prod = data.production_date if data.production_date and data.production_date|length == 7 else '' %}
{% if exact_prod %}<input type=hidden name=production_month value="{{exact_prod}}">{% else %}<label>Месяц и год производства (MM.YYYY)</label><input name=production_month value="{{calc.production_month if calc else ''}}" placeholder="Например, 02.2021" pattern="(0[1-9]|1[0-2])\.[0-9]{4}" required><p>Encar не передал точный месяц. Укажи его по документам автомобиля — не по модельному году.</p>{% endif %}
{% if data.power_hp is none or data.power_hp == '' %}<label>Мощность двигателя, л.с.</label><input name=power_hp type=number min=1 max=2000 step=1 required placeholder="Например, 150">{% else %}<input type=hidden name=power_hp value="{{data.power_hp}}">{% endif %}
{% if not data.fuel %}<label>Тип топлива (не найден в Encar — укажи вручную)</label><select name=manual_fuel required><option value="">Выбери тип топлива</option>{% for v in ['Бензин','Дизель','Гибрид','Подключаемый гибрид (PHEV)','Электро','Газ/LPG','Бензин/газ','Другое'] %}<option value="{{v}}" {% if calc and calc.manual_fuel == v %}selected{% endif %}>{{v}}</option>{% endfor %}</select>{% else %}<input type=hidden name=manual_fuel value="">{% endif %}
{% if not data.transmission %}<label>Тип трансмиссии (не найден в Encar — укажи вручную)</label><select name=manual_transmission required><option value="">Выбери трансмиссию</option>{% for v in ['Механическая','Классический автомат','Робот (DCT/DSG)','Вариатор (CVT)','Одноступенчатая (электромобиль)','Другая'] %}<option value="{{v}}" {% if calc and calc.manual_transmission == v %}selected{% endif %}>{{v}}</option>{% endfor %}</select>{% else %}<input type=hidden name=manual_transmission value="">{% endif %}
<div id="recycleBox" {% if data.power_hp is not none and data.power_hp != '' and data.power_hp|float <= 160 %}style="display:none"{% endif %}><label>Подтверждённый утильсбор, ₽ (обязателен при мощности выше 160 л.с.)</label><input id="manual_recycle" name="manual_recycle" value="{{calc.manual_recycle if calc and calc.manual_recycle is not none else ''}}" type=number min=0 step=1 placeholder="Сумма по калькулятору Drom"></div>
<button id="calcButton">Рассчитать стоимость</button></form>
<script>(function(){const hp=document.querySelector('[name=power_hp]'),box=document.getElementById('recycleBox'),fee=document.getElementById('manual_recycle');function sync(){if(!hp||!box)return;const required=Number(hp.value)>160;box.style.display=required?'block':'none';if(fee)fee.required=required;}if(hp){hp.addEventListener('input',sync);sync();}})();</script>
<script>
(function(){
 const hpKnown = {{ 'true' if data.power_hp is not none and data.power_hp != '' else 'false' }};
 const box=document.getElementById('hpMissing'), field=document.getElementById('power_hp');
 if(!hpKnown){ box.style.display='block'; field.required=true; }
})();
</script>
{% if calc %}<div class=item><b>Предварительная цена до Москвы: {{'{:,.0f}'.format(calc.total).replace(',', ' ')}} ₽</b><br>
Авто + расходы Кореи: {{'{:,.0f}'.format(calc.krw_total).replace(',', ' ')}} ₩<br>
Курс: {{calc.rate}} ₽ за 1 000 ₩ · EUR/RUB: {{calc.eur_rate}}<br>
Возраст: {{calc.age_label}}<br>Таможенные платежи (оценка): {{'{:,.0f}'.format(calc.customs_duty + calc.customs_adjustment).replace(',', ' ')}} ₽<br>
Утилизационный сбор: {{'{:,.0f}'.format(calc.recycle_fee).replace(',', ' ')}} ₽<br>Расходы РФ: {{'{:,.0f}'.format(calc.ru_extra).replace(',', ' ')}} ₽</div>
{% if calc.warnings %}<div class=item><b>Важно:</b><ul>{% for warning in calc.warnings %}<li>{{warning}}</li>{% endfor %}</ul></div>{% endif %}
{% if calc.publishable %}<form method=post action=/publish><input type=hidden name=car_id value="{{data.id}}"><input type=hidden name=rate value="{{calc.rate}}"><input type=hidden name=eur_rate value="{{calc.eur_rate}}"><input type=hidden name=customs_adjustment value="{{calc.customs_adjustment}}"><input type=hidden name=manual_recycle value="{{calc.manual_recycle if calc.manual_recycle is not none else ''}}"><input type=hidden name=power_hp value="{{calc.power_hp if calc and calc.power_hp is not none else (data.power_hp if data.power_hp is not none else '')}}"><input type=hidden name=manual_fuel value="{{calc.manual_fuel if calc else ''}}"><input type=hidden name=manual_transmission value="{{calc.manual_transmission if calc else ''}}"><input type=hidden name=kr_extra value="{{calc.kr_extra}}"><input type=hidden name=ru_extra value="{{calc.ru_extra}}"><button>Опубликовать в Telegram</button></form>{% else %}<b>Публикация заблокирована: уточни обязательные данные и пересчитай.</b>{% endif %}{% endif %}

{% endif %}<script>function toggleEdit(key){const sel=document.getElementById(key+'Edit');sel.hidden=!sel.hidden;if(!sel.hidden)sel.focus();}</script></html>"""

def getid(v):
    v=(v or "").strip()
    if v.isdigit(): return v
    p=urlparse(v if "://" in v else "https://"+v); q=parse_qs(p.query)
    for k in ("carid","vehicleId","vehicle_id","id"):
        if q.get(k) and q[k][0].isdigit(): return q[k][0]
    m=re.search(r"/(?:cars/detail/)?(\d{7,10})(?:\D|$)",p.path)
    return m.group(1) if m else None

def api(path):
    key=os.environ.get("XAPI_KOREA_API_KEY","").strip()
    if not key:return None,"Не задан XAPI_KOREA_API_KEY в Vercel."
    try:
        r=requests.get(BASE+path,headers={"X-API-Key":key,"Accept":"application/json"},timeout=18)
        if r.status_code == 429:
            retry_after = (r.headers.get("Retry-After") or "").strip()
            suffix = f" Повтори не раньше чем через {retry_after} сек." if retry_after.isdigit() else " Подожди 60 секунд перед следующей попыткой."
            return None,"XAPI временно ограничил запросы (HTTP 429): превышен лимит бесплатного тарифа." + suffix
        if r.status_code!=200:return None,f"XAPI HTTP {r.status_code}: {r.text[:180]}"
        return r.json(),None
    except Exception as e:return None,"Ошибка XAPI: "+str(e)[:160]

def unwrap(x):
    while isinstance(x,dict):
        nxt=next((x[k] for k in ("data","car","vehicle","result") if isinstance(x.get(k),dict)),None)
        if nxt is None:break
        x=nxt
    return x

def norm_key(s): return re.sub(r"[^a-z0-9]","",str(s).lower())

def find_value(obj,aliases):
    if not isinstance(obj,dict):return None
    names={norm_key(a) for a in aliases}
    for k,v in obj.items():
        if norm_key(k) in names and v not in (None,"",[],{}):return v
    for v in obj.values():
        if isinstance(v,dict):
            got=find_value(v,aliases)
            if got not in (None,"",[],{}):return got
    return None

def clean(v):
    if isinstance(v,dict):
        for k in ("name","label","value","text","displayName","display_name","title","code"):
            if v.get(k) not in (None,"",[],{}):return clean(v[k])
        return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):
        a=[clean(x) for x in v if x not in (None,"",[],{})]
        return ", ".join(map(str,a)) if a else None
    if isinstance(v,str):return v.strip() or None
    return v

def val(d,aliases):return clean(find_value(d,aliases))

def urls(x):
    out=[]
    def walk(v):
        if isinstance(v,dict):
            for k,z in v.items():
                if isinstance(z,str) and z.startswith(("https://","http://","//")) and any(a in k.lower() for a in ("image","photo","url","picture","thumbnail")):out.append("https:"+z if z.startswith("//") else z)
                else:walk(z)
        elif isinstance(v,list):
            for z in v:
                if isinstance(z,str) and z.startswith(("https://","http://","//")):out.append("https:"+z if z.startswith("//") else z)
                else:walk(z)
    walk(x)
    return list(dict.fromkeys(u for u in out if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)|image|photo|encar|carpicture",u,re.I)))


def normalize_fuel(value):
    """Normalize fuel labels only when the source gives an explicit recognizable value."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    key = re.sub(r"[\s_\-/]+", " ", raw.casefold()).strip()
    # Explicit source labels, including Korean labels used by Encar.
    aliases = [
        (("gasoline", "gasoline engine", "petrol", "휘발유", "가솔린", "бензин", "бензиновый"), "Бензин"),
        (("diesel", "diesel engine", "경유", "디젤", "дизель", "дизельный"), "Дизель"),
        (("hybrid", "hev", "하이브리드", "гибрид", "гибридный"), "Гибрид"),
        (("lpg", "liquefied petroleum gas", "autogas", "엘피지", "lpi", "газ", "газовое"), "Газ"),
        (("electric", "ev", "전기", "электро", "электрический"), "Электро"),
        (("hydrogen", "수소", "водород"), "Водород"),
    ]
    for variants, label in aliases:
        if any(v in key for v in variants):
            return label
    # Preserve unknown source text for operator review; never silently default to petrol.
    return raw


def format_production_date(raw):
    """Normalize exact month/year values; never invent a month from a model year."""
    if raw is None: return None
    s=str(raw).strip()
    # Common Encar/API forms: YYYYMM, YYYY-MM, YYYY/MM, YYYY.MM
    m=re.fullmatch(r"(\d{4})(\d{2})",s)
    if m:
        year,month=int(m.group(1)),int(m.group(2))
        if 1 <= month <= 12: return f"{month:02d}.{year:04d}"
    m=re.fullmatch(r"(\d{4})[-/.](\d{1,2})",s)
    if m:
        year,month=int(m.group(1)),int(m.group(2))
        if 1 <= month <= 12: return f"{month:02d}.{year:04d}"
    # A year-only value remains a year and is not accepted as a production month.
    m=re.fullmatch(r"(\d{4})",s)
    if m: return s
    # Already normalized MM.YYYY
    if re.fullmatch(r"(0[1-9]|1[0-2])\.\d{4}",s): return s
    return s

def apply_verified_drom_reference(fields):
    """Only fill specs for an exact known match; otherwise preserve missing values."""
    brand=str(fields.get("brand") or "").lower()
    model=str(fields.get("model") or "").lower()
    trim=str(fields.get("trim") or "").lower()
    title=str(fields.get("title") or "").lower()
    # Encar/XAPI sometimes puts the useful model/trim text only in the title.
    identity=" ".join((brand, model, trim, title))
    fuel=str(fields.get("fuel") or "").lower()
    trans=str(fields.get("transmission") or "").lower()
    engine=str(fields.get("engine_cc") or "").lower().replace(",", "").replace(" ", "")
    date=str(fields.get("production_date_raw") or "")
    # Drom's Korean-market BMW F40 118d AT Joy: 1995 cc, 150 hp, front-wheel drive.
    # Drom production period 07.2019–07.2021, matching this listing's 02.2021 date.
    exact_bmw_match = (
        "bmw" in brand and "1 series" in model and "f40" in model
        and "118d" in trim and "joy" in trim
        and ("diesel" in fuel or "диз" in fuel)
        and ("automatic" in trans or "автомат" in trans or "at" == trans)
        and ("1995" in engine or "2.0" in engine)
    )
    exact_stonic_match = (
        ("kia" in identity or "기아" in identity) and "stonic" in identity
        and ("1.4" in identity or "1368" in engine or "1368cc" in engine or "g4lc" in identity)
        and ("prestige" in identity or "프레스티지" in identity)
        and ("1368" in engine or "1.4" in identity or "g4lc" in identity)
        and (not fuel or "бенз" in fuel or "gasoline" in fuel or "petrol" in fuel or "휘발유" in fuel)
    )
    if exact_bmw_match:
        fields["power_hp"] = fields.get("power_hp") or 150
        fields["power_kw"] = fields.get("power_kw") or 110
        fields["drive"] = fields.get("drive") or "Передний (FF)"
        fields["specification_source"] = "Drom: BMW 1-Series 118d AT Joy"
        fields["specification_source_url"] = "https://www.drom.ru/catalog/bmw/1-series/542277/"
        fields["specification_match"] = "matched"
        fields["specification_note"] = "Мощность и привод дополнены по совпадающей модификации Drom; проверь VIN/комплектацию перед таможенным расчётом."
    elif exact_stonic_match:
        # Korean-market Kia Stonic 1.4 MPI AT 2WD Prestige (engine G4LC, 1,368 cc): 100 PS / 74 kW.
        # Source: Drom exact trim specification; do not apply to 1.0 T-GDI or 1.6 diesel variants.
        fields["power_hp"] = fields.get("power_hp") or 100
        fields["power_kw"] = fields.get("power_kw") or 74
        fields["drive"] = fields.get("drive") or "Передний (FF)"
        fields["specification_source"] = "Drom: Kia Stonic 1.4 MPi AT 2WD Prestige"
        fields["specification_source_url"] = "https://www.drom.ru/catalog/kia/stonic/438745/"
        fields["specification_match"] = "matched"
        fields["specification_note"] = "Мощность дополнена по совпадающей модификации Kia Stonic 1.4 MPI 1368 см³; перед таможенным расчётом проверь данные документов."
    else:
        fields["specification_source"] = None
        fields["specification_source_url"] = fields.get("drom_check_url")
        fields["specification_match"] = "not_matched"
        fields["specification_note"] = "Encar/XAPI и таблица точных проверенных модификаций не дали подтверждённую мощность. Значение не угадывается; требуется ручная проверка по VIN/двигателю и источнику спецификаций."
    return fields

def apply_verified_transmission_reference(fields):
    """Apply gearbox corrections only for known exact Korean-market configurations."""
    searchable = " ".join(str(fields.get(k) or "") for k in ("title", "brand", "model", "trim")).casefold()
    fuel = str(fields.get("fuel") or "").casefold()
    transmission = str(fields.get("transmission") or "").casefold()
    generic_automatic = any(token in transmission for token in ("automatic", "자동", "auto"))

    # Hyundai Avante/Elantra Hybrid CN7 uses a 6-speed DCT in this configuration.
    is_hyundai = "hyundai" in searchable or "현대" in searchable
    is_cn7 = "cn7" in searchable
    is_avante_elantra = "avante" in searchable or "elantra" in searchable
    is_hybrid = "hybrid" in searchable or "hev" in searchable or "하이브리드" in searchable or "hybrid" in fuel or "hev" in fuel
    if is_hyundai and is_cn7 and is_avante_elantra and is_hybrid and generic_automatic:
        fields["transmission"] = "Робот (6-ступ. DCT)"
        fields["transmission_source"] = "проверенная спецификация Hyundai Avante/Elantra Hybrid CN7"
        return fields

    # Korean-market Kia K3/Cerato BD sedan, 1.6 MPI 123 PS Prestige (2021 facelift): IVT/CVT.
    # Restrict this correction to the known naturally aspirated 1.6 configuration; never infer
    # gearbox type for GT/turbo or other generations from the generic word "Automatic" alone.
    is_kia = "kia" in searchable or "기아" in searchable
    is_k3_cerato = "k3" in searchable or "cerato" in searchable or "forte" in searchable
    is_bd = "bd" in searchable or "2nd gen" in searchable or "2nd generation" in searchable or "the new k3" in searchable
    is_16 = any(token in searchable for token in ("1.6", "1598", "1600"))
    is_prestige = "prestige" in searchable
    is_non_turbo = not any(token in searchable for token in ("gt", "turbo", "204 hp", "204ps"))
    power = str(fields.get("power_hp") or "").strip()
    engine = str(fields.get("engine_cc") or "").strip().casefold()
    is_123ps = power in ("123", "123.0", "123.00")
    is_1598cc = "1598" in engine
    if (is_kia and is_k3_cerato and is_bd and is_16 and is_prestige and is_non_turbo
            and generic_automatic and (is_123ps or is_1598cc)):
        fields["transmission"] = "Вариатор (CVT)"
        fields["transmission_source"] = "проверенная спецификация Kia K3 BD 1.6 MPI CVT Prestige"
    return fields


def translate_vehicle_text(value):
    """Return English vehicle make/model/trim text; prefer explicit English source fields."""
    if value in (None, ""):
        return value
    text = str(value).strip()
    # Makes and model names commonly returned in Korean by Encar.
    terms = [
        ("메르세데스-벤츠", "Mercedes-Benz"), ("르노코리아", "Renault Korea"),
        ("KG모빌리티", "KG Mobility"), ("랜드로버", "Land Rover"),
        ("르노삼성", "Renault Samsung"), ("비엠더블유", "BMW"),
        ("쉐보레", "Chevrolet"), ("폭스바겐", "Volkswagen"),
        ("제네시스", "Genesis"), ("쌍용", "SsangYong"),
        ("현대", "Hyundai"), ("기아", "Kia"), ("지프", "Jeep"),
        ("벤츠", "Mercedes-Benz"), ("아우디", "Audi"), ("볼보", "Volvo"),
        ("토요타", "Toyota"), ("렉서스", "Lexus"), ("혼다", "Honda"),
        ("닛산", "Nissan"), ("포드", "Ford"), ("테슬라", "Tesla"), ("미니", "MINI"),
        ("레니게이드", "Renegade"), ("그랜드 체로키", "Grand Cherokee"),
        ("체로키", "Cherokee"), ("랭글러", "Wrangler"), ("컴패스", "Compass"),
        ("쏘렌토", "Sorento"), ("스포티지", "Sportage"), ("셀토스", "Seltos"),
        ("카니발", "Carnival"), ("쏘울", "Soul"), ("모닝", "Morning"),
        ("레이", "Ray"), ("K3", "K3"), ("K5", "K5"), ("K7", "K7"), ("K8", "K8"),
        ("아반떼", "Avante"), ("쏘나타", "Sonata"), ("그랜저", "Grandeur"),
        ("투싼", "Tucson"), ("싼타페", "Santa Fe"), ("팰리세이드", "Palisade"),
        ("코나", "Kona"), ("캐스퍼", "Casper"), ("베뉴", "Venue"),
        ("아이오닉", "Ioniq"), ("제네시스 G70", "Genesis G70"),
        ("제네시스 G80", "Genesis G80"), ("제네시스 GV70", "Genesis GV70"),
        ("제네시스 GV80", "Genesis GV80"), ("티볼리", "Tivoli"),
        ("토레스", "Torres"), ("렉스턴", "Rexton"), ("QM6", "QM6"),
        ("SM6", "SM6"), ("마스터", "Master"), ("플러그인 하이브리드", "Plug-in Hybrid"),
        ("하이브리드", "Hybrid"), ("디젤", "Diesel"), ("가솔린", "Gasoline"),
        ("휘발유", "Gasoline"), ("리미티드", "Limited"), ("프레스티지", "Prestige"),
        ("노블레스", "Noblesse"), ("시그니처", "Signature"),
        ("익스클루시브", "Exclusive"), ("인스퍼레이션", "Inspiration"),
        ("프리미엄", "Premium"), ("럭셔리", "Luxury"), ("모던", "Modern"),
        ("스마트", "Smart"), ("스포츠", "Sport"), ("프라임", "Prime"),
        ("어반", "Urban"), ("캘리그래피", "Calligraphy"), ("터보", "Turbo"),
        ("전기", "Electric"), ("디럭스", "Deluxe"), ("프레스티지", "Prestige"),
        ("장애인", "Mobility Support"), ("일반", "Standard"),
    ]
    for korean, english in sorted(terms, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(korean, english)
    # Do not display untranslated Hangul in the make/model/trim fields.
    # If an uncommon name has no dictionary entry, retain its Latin/numeric parts only.
    text = re.sub(r"[\\uac00-\\ud7a3]+", "", text)
    text = re.sub(r"\\s+", " ", text).strip(" -·/")
    return text or None


def parse(cid):
    d,e=api(f"/cars/{cid}?lang=en")
    base={"id":cid,"photos":[],"missing_fields":[],"drom_calc_url":"https://www.drom.ru/world/calculator/korea/","tks_calc_url":"https://www.tks.ru/auto/calc/main/"}
    if e:return {**base,"status":"failed","error":e,"missing_fields":["all"]}
    d=unwrap(d)
    if not isinstance(d,dict):return {**base,"status":"failed","error":"Неожиданный формат ответа XAPI","missing_fields":["all"]}
    im,imerr=api(f"/cars/{cid}/images")
    photos=urls(im) if im is not None else []
    if not photos:photos=urls(d)
    # fallback to Encar photo fields when represented as strings/list
    photos=(photos or urls({"photos":d.get("photos"),"thumbnail":d.get("thumbnail")}))[:MAX_PHOTOS]

    brand=translate_vehicle_text(val(d,["manufacturer_en","make_en","brand_en","manufacturer","brand","make"]))
    model=translate_vehicle_text(val(d,["model_en","model_name_en","vehicle_model_en","model","model_name","vehicle_model"]))
    # IMPORTANT: badge / badge_detail represent Encar's trim; options are equipment, not trim.
    badge=translate_vehicle_text(val(d,["badge_en","trim_en","badge"]))
    badge_detail=translate_vehicle_text(val(d,["badge_detail_en","badge_detail","badgeDetail"]))
    trim=" ".join(x for x in (badge,badge_detail) if x) or translate_vehicle_text(val(d,["trim_en","grade_en","trim","trim_name","grade","vehicle_grade"]))
    api_title=translate_vehicle_text(val(d,["title_en","vehicle_title_en","listing_title_en","title","vehicle_title","listing_title","name"]))
    title=api_title or " ".join(x for x in (brand,model,trim) if x) or None

    # XAPI field names vary between listing types. Prefer explicit year-month fields.
    production_raw=val(d,["year_month","yearMonth","production_date","manufacture_date",
                          "manufacturing_date","manufactureDate","productionDate","made_year_month",
                          "madeYearMonth","date_of_manufacture","model_year_month"])
    # `form_year` is only a fallback: it often contains the model year, not the exact production month.
    if not production_raw:
        production_raw=val(d,["form_year"])
    if not production_raw:
        # Search nested response objects for a field whose name explicitly indicates production month/date.
        production_raw=find_value(d,["year_month","yearMonth","production_date","manufacture_date",
                                     "manufacturing_date","manufactureDate","productionDate",
                                     "made_year_month","madeYearMonth","date_of_manufacture"])
        production_raw=clean(production_raw)
    # Some XAPI listing responses expose the exact production month in `year` as YYYYMM
    # while `form_year` contains only YYYY. Prefer YYYYMM only when it is explicitly present.
    if not re.fullmatch(r"\d{4}\d{2}", str(production_raw or "").strip()):
        year_month_candidate=val(d,["year","yearMonth","year_month"])
        if re.fullmatch(r"\d{6}", str(year_month_candidate or "").strip()):
            production_raw=year_month_candidate
    # Normalize/repair displacement for the exact Mercedes-Benz GLB 200 d X247
    # listing when XAPI omits it. The 2.0 diesel is 1,950 cc; keep cc for calculations.
    engine_cc_value=val(d,["engine_cc","displacement","engine_size","cc","engineDisplacement","engine_capacity","engineCapacity","displacement_cc","engine_volume"])
    if engine_cc_value in (None, ""):
        searchable=" ".join(str(x or "") for x in (title,brand,model,trim)).lower()
        fuel_text=str(val(d,["fuel_type","fuel","fuelType"]) or "").lower()
        if ("mercedes" in searchable or "벤츠" in searchable) and "glb" in searchable and "200 d" in searchable and ("x247" in searchable or "diesel" in fuel_text or "디젤" in fuel_text or "диз" in fuel_text):
            engine_cc_value=1950
    fields={
      "title":title,"brand":brand,"model":model,"trim":trim,
      "price_krw":val(d,["price_krw","original_price_krw","priceKrw","price","sale_price"]),
      "mileage_km":val(d,["mileage_km","mileage","mileageKm","distance"]),
      "production_date_raw":production_raw,
      "production_date":format_production_date(production_raw),
      "production_date_source":"Encar/XAPI" if production_raw else None,
      "engine_cc":engine_cc_value,
      "power_hp":val(d,["power_hp","horsepower","horse_power","power_hp_ps","engine_power_hp","enginePowerHp","engine_power_ps","enginePowerPs","horsepower_ps","horsePowerPs","powerPs","max_power_ps","maxPowerPs","output_ps","engineOutputPs","ps","hp","horsepowerPs","engine_power","enginePower","max_power","maxPower","rated_power_ps","ratedPowerPs"]),
      "power_kw":val(d,["power_kw","engine_power_kw","enginePowerKw","horsepower_kw","horsePowerKw","max_power_kw","maxPowerKw","output_kw","engineOutputKw","rated_power_kw","ratedPowerKw","kw"]),
      "fuel":normalize_fuel(val(d,["fuel_type","fuel","fuelType"])),
      "transmission":val(d,["transmission","gearbox","transmission_type"]),
      "drive":val(d,["drive_type","drive","driveType","drivetrain","driving_method"]),
      "vin":val(d,["vin","vehicle_identification_number"]),
      "vehicle_no":val(d,["vehicle_no","vehicle_number","plate_number"]),
      "year":val(d,["form_year","year","model_year"])
    }
    # Correct contradictory/missing fuel labels when the exact listing title/model explicitly identifies a hybrid.
    # Encar may expose the combustion component as gasoline even for a hybrid vehicle.
    listing_identity = " ".join(str(fields.get(k) or "") for k in ("title", "brand", "model", "trim")).casefold()
    hybrid_markers = ("hybrid", "hev", "하이브리드", "гибрид")
    if any(marker in listing_identity for marker in hybrid_markers):
        fields["fuel"] = "Гибрид"

    # If API exposes power only in kW, convert to metric horsepower (PS) for customs thresholds.
    # Never infer power when both fields are absent.
    if not fields.get("power_hp") and fields.get("power_kw") not in (None, ""):
        try:
            fields["power_hp"] = round(float(re.search(r"[0-9]+(?:[.,][0-9]+)?", str(fields["power_kw"])).group(0).replace(",", ".")) * 1.35962)
            fields["power_hp_source"] = "converted from XAPI kW"
        except (AttributeError, ValueError):
            fields["power_hp"] = None
    # Drive type is useful descriptive information but does not affect the price calculation.
    # Do not block an otherwise valid calculation/publication solely because XAPI omits it.
    missing=[k for k in ("title","brand","model","trim","price_krw","mileage_km","production_date","engine_cc","fuel","transmission","vin","photos") if (not fields.get(k) if k!="photos" else not photos)]
    fields["optional_missing_fields"] = [k for k in ("drive",) if not fields.get(k)]
    q=quote_plus(" ".join(x for x in (brand,model,trim) if x))
    fields.update(base)
    fields.update({"photos":photos,"missing_fields":missing,"photo_endpoint_error":imerr,"raw_field_names":sorted(str(k) for k in d.keys()),
                   "drom_check_url":"https://www.drom.ru/catalog/?q="+q,
                   "status":"ready_for_manual_review" if photos and fields["price_krw"] is not None else "failed_for_publication",
                   "warning":"Комплектация берётся из badge/badge_detail; options показываются отдельно. Если мощность или привод отсутствуют в API, проверь точную модификацию на Drom — не угадываем."})
    fields=apply_verified_drom_reference(fields)
    fields=apply_verified_transmission_reference(fields)
    # Recalculate missing fields after applying an exact verified reference match.
    fields["missing_fields"]=[k for k in ("title","brand","model","trim","price_krw","mileage_km","production_date","engine_cc","fuel","transmission","vin","photos")
                              if (not fields.get(k) if k!="photos" else not fields.get("photos"))]
    fields["optional_missing_fields"] = [k for k in ("drive",) if not fields.get(k)]
    return fields


def fetch_rates():
    """Fetch the latest official CBR rates; KRW is quoted per 1000 units."""
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    response = requests.get(url, timeout=15, headers={"User-Agent":"NIKA-MOTORS/1.0"})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rates = {}
    for item in root.findall("Valute"):
        char_code = (item.findtext("CharCode") or "").strip().upper()
        nominal = float((item.findtext("Nominal") or "1").replace(",", "."))
        value = float((item.findtext("Value") or "0").replace(",", "."))
        if nominal > 0 and value > 0:
            rates[char_code] = value / nominal
    if "EUR" not in rates or "KRW" not in rates:
        raise ValueError("Банк России не вернул курс EUR и/или KRW.")
    return {
        "eur_rub": rates["EUR"],
        "krw_rub_per_1000": rates["KRW"] * 1000,
        "source": "Банк России",
        "date": root.attrib.get("Date") or datetime.now(timezone.utc).strftime("%d.%m.%Y")
    }

def telegram_send(fields, calc):
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    # Default destination: Telegram forum/group @nikamotors, topic ID 5.
    # Telegram API needs chat_id and message_thread_id separately; a t.me URL
    # is parsed below. Explicit environment variables override these defaults.
    default_target = "@nikamotors"
    chat=os.environ.get("TELEGRAM_CHAT_ID", default_target).strip()
    thread=os.environ.get("TELEGRAM_MESSAGE_THREAD_ID", "5").strip()
    if chat.startswith(("https://t.me/", "http://t.me/", "t.me/")):
        channel_path=chat.removeprefix("https://").removeprefix("http://").removeprefix("t.me/").strip("/")
        parts=[part for part in channel_path.split("/") if part]
        if parts and not parts[0].startswith(("+", "joinchat")):
            chat="@" + parts[0]
            # Use the URL's final segment as topic/thread ID unless explicitly overridden.
            if len(parts) >= 2 and not thread and parts[-1].isdigit():
                thread=parts[-1]
    if not token: raise ValueError("Не задан TELEGRAM_BOT_TOKEN.")
    if not fields.get("photos"): raise ValueError("Нет фотографий — публикация отменена.")
    caption=make_post(fields,calc)
    thread_id=int(thread) if thread else None
    photos=fields["photos"][:10]
    if len(photos)==1:
        payload={"chat_id":chat,"photo":photos[0],"caption":caption,"parse_mode":"HTML"}
        if thread_id is not None: payload["message_thread_id"]=thread_id
        response=requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",json=payload,timeout=25)
    else:
        media=[]
        for i,url in enumerate(photos):
            item={"type":"photo","media":url}
            if i==0:
                item["caption"]=caption
                item["parse_mode"]="HTML"
            media.append(item)
        payload={"chat_id":chat,"media":media}
        if thread_id is not None: payload["message_thread_id"]=thread_id
        response=requests.post(f"https://api.telegram.org/bot{token}/sendMediaGroup",json=payload,timeout=25)
    try: result=response.json()
    except Exception: result={}
    if not response.ok or not result.get("ok",False):
        description = str(result.get("description") or response.text or "Unknown Telegram API error")
        if "chat not found" in description.lower():
            raise ValueError(
                "Telegram API: chat not found. Проверьте TELEGRAM_CHAT_ID "
                "(для канала укажите @username или числовой ID) и убедитесь, "
                "что бот из TELEGRAM_BOT_TOKEN добавлен в этот канал "
                "администратором с правом публикации."
            )
        raise ValueError(f"Telegram API: HTTP {response.status_code}: {description[:250]}")
    return result

@app.route("/auto-publish", methods=["POST"])
def auto_publish():
    raw=request.form.get("car","").strip()
    car_id=getid(raw)
    if not car_id:
        return render_template_string("<!doctype html><html lang=ru><meta name=viewport content='width=device-width,initial-scale=1'><body style='font:16px system-ui;background:#111;color:#eee;padding:24px'><h2>Не удалось распознать ссылку</h2><p>Проверь ссылку Encar и попробуй ещё раз.</p><p><a style='color:#9ecbff' href='/'>Вернуться</a></p></body></html>"),400
    try:
        fields=parse(car_id)
        if fields.get("status") != "ready_for_manual_review":
            msg="Не удалось получить карточку Encar. " + str(fields.get("error") or fields.get("missing_fields"))
            return render_template_string("<!doctype html><html lang=ru><meta name=viewport content='width=device-width,initial-scale=1'><body style='font:16px system-ui;background:#111;color:#eee;padding:24px'><h2>Автопубликация остановлена</h2><p>{{msg}}</p><p><a style='color:#9ecbff' href='/'>Вернуться к парсеру</a></p></body></html>",msg=msg),400
        rates=fetch_rates()
        # Missing horsepower must be entered by the operator; never substitute 159 hp.
        if fields.get("power_hp") in (None, "") or not fields.get("fuel") or not fields.get("transmission"):
            # Ask only for the values genuinely missing from Encar; keep routine
            # calculator settings at their configured defaults.
            prod=fields.get("production_date") or ""
            prod=prod if re.fullmatch(r"(0[1-9]|1[0-2])\.\d{4}",str(prod)) else ""
            return render_template_string("""<!doctype html><html lang=ru><meta name=viewport content='width=device-width,initial-scale=1'><style>body{font:17px system-ui;background:#111;color:#eee;padding:22px;max-width:720px;margin:auto}input,button{font:inherit;width:100%;box-sizing:border-box;padding:13px;margin:8px 0 18px;border-radius:9px;border:1px solid #555}input{background:#fff;color:#111}button{background:#b71c1c;color:white;border:0;font-weight:700}label{display:block;margin-top:10px}a{color:#9ecbff}</style><h2>Нужно уточнить данные автомобиля</h2><p>Для автомобиля <b>{{title}}</b> (VIN: {{vin or 'не указан'}}) не хватает характеристик. Заполни вручную только те поля, которые Encar/XAPI не вернул.</p><form method=post action='/calculate'><input type=hidden name=car_id value='{{car_id}}'><input type=hidden name=rate value='{{default_rate}}'><input type=hidden name=eur_rate value='{{default_eur_rate}}'><input type=hidden name=customs_adjustment value='0'><input type=hidden name=kr_extra value='1740000'><input type=hidden name=ru_extra value='450000'>{% if not hp %}<label>Мощность двигателя, л.с.</label><input name=power_hp type=number min=1 max=2000 step=1 required placeholder='Например, 150'>{% else %}<input type=hidden name=power_hp value='{{hp}}'>{% endif %}{% if not fuel %}<label>Тип топлива</label><select name=manual_fuel required><option value=''>Выбери тип топлива</option>{% for v in ['Бензин','Дизель','Гибрид','Подключаемый гибрид (PHEV)','Электро','Газ/LPG','Бензин/газ','Другое'] %}<option value='{{v}}'>{{v}}</option>{% endfor %}</select>{% endif %}{% if not transmission %}<label>Тип трансмиссии</label><select name=manual_transmission required><option value=''>Выбери трансмиссию</option>{% for v in ['Механическая','Классический автомат','Робот (DCT/DSG)','Вариатор (CVT)','Одноступенчатая (электромобиль)','Другая'] %}<option value='{{v}}'>{{v}}</option>{% endfor %}</select>{% endif %}<label>Месяц и год производства (MM.YYYY)</label><input name=production_month value='{{prod}}' placeholder='Например, 02.2021' pattern='(0[1-9]|1[0-2])\.[0-9]{4}' required><p>Месяц подставлен автоматически, только если он действительно пришёл из Encar. Если поле пустое, API не передал точный месяц — укажи его по данным автомобиля, не по модельному году.</p><button>Рассчитать стоимость</button></form><a href='/'>Вернуться</a><script>function toggleEdit(key){const sel=document.getElementById(key+'Edit');sel.hidden=!sel.hidden;if(!sel.hidden)sel.focus();}</script></html>""",car_id=car_id,title=fields.get("title") or "автомобиля",vin=fields.get("vin"),hp=fields.get("power_hp"),fuel=fields.get("fuel"),transmission=fields.get("transmission"),prod=prod,default_rate=rates['krw_rub_per_1000'],default_eur_rate=rates['eur_rub']),200
        # Never invent production month. If Encar has only a year, block and report instead of guessing.
        prod=fields.get("production_date")
        if not prod or not re.fullmatch(r"(0[1-9]|1[0-2])\.\d{4}",str(prod)):
            msg=("Encar/XAPI не вернул подтверждённый месяц производства. Система не будет угадывать возраст машины, "
                 "так как от него зависит таможня. Дата, полученная из API: " + str(fields.get("production_date_raw") or "нет данных"))
            return render_template_string("<!doctype html><html lang=ru><meta name=viewport content='width=device-width,initial-scale=1'><body style='font:16px system-ui;background:#111;color:#eee;padding:24px'><h2>Автопубликация остановлена</h2><p>{{msg}}</p><p>Открой карточку Encar и проверь поле даты выпуска. После исправления парсера можно повторить отправку.</p><p><a style='color:#9ecbff' href='/'>Вернуться к парсеру</a></p></body></html>",msg=msg),400
        form={
            "rate":str(rates["krw_rub_per_1000"]),
            "eur_rate":str(rates["eur_rub"]),
            "production_month":"",
            "customs_adjustment":os.environ.get("CUSTOMS_ADJUSTMENT_RUB","0"),
            "manual_recycle":os.environ.get("MANUAL_RECYCLE_RUB",""),
            "kr_extra":os.environ.get("KR_EXTRA_KRW","1740000"),
            "ru_extra":os.environ.get("RU_EXTRA_RUB","450000")
        }
        fields,calc=calc_values(car_id,form)
        if not calc.get("publishable"):
            return "Автопубликация остановлена: не хватает обязательных подтверждённых данных или утильсбора. " + ", ".join(fields.get("missing_fields",[])),400
        # Add explicit rate provenance to the caption.
        calc["warnings"].append(f"Курсы автоматически загружены: {rates['source']}, дата данных {rates['date']}.")
        telegram_send(fields,calc)
        return ("<html lang=ru><meta name=viewport content='width=device-width,initial-scale=1'><body style='background:#111;color:#eee;font:18px system-ui;padding:20px'>"
                "<h2>Готово: объявление отправлено в Telegram</h2><p>Курсы EUR/RUB и KRW/RUB загружены автоматически. Источник: "
                + rates["source"] + ". Итоговая цена включена в публикацию.</p><a style='color:#9ecbff' href='/'>Добавить следующий автомобиль</a></body></html>")
    except Exception as e:
        return "Автоматический расчёт/публикация не выполнены: " + str(e)[:350],400


@app.route("/",methods=["GET","POST"])
def home():
    car="";data=None;data_json=""
    if request.method=="POST":
        car=request.form.get("car","");cid=getid(car)
        data=parse(cid) if cid else {"status":"failed","error":"Не удалось извлечь ID из ссылки","photos":[],"missing_fields":["valid ID"]}
        data_json=json.dumps(data,ensure_ascii=False,indent=2)
    return render_template_string(HTML,car=car,data=data,data_json=data_json,calc=None,default_rate=os.environ.get('KRW_RUB_PER_1000','63.78'),default_eur_rate=os.environ.get('EUR_RUB_RATE',''))


def _number(value, label, allow_blank=False, default=None):
    if value in (None, ""):
        if allow_blank: return default
        raise ValueError(f"Не указано поле: {label}")
    raw=str(value).strip()
    try:
        n=float(raw.replace(",", "."))
    except Exception:
        # Encar/XAPI may return displacement as text, e.g. "1995cc" or "1995 cc".
        # Accept a numeric value followed only by a known unit; reject arbitrary text.
        m=re.fullmatch(r"\s*([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))\s*(?:cc|cm³|cm3|см³|см3|л\.?с\.?|kw|квт)?\s*", raw, re.I)
        if not m:
            raise ValueError(f"Некорректное число: {label}")
        n=float(m.group(1).replace(",", "."))
    if n < 0: raise ValueError(f"{label}: значение не может быть отрицательным")
    return n

def _production_month(raw):
    s=str(raw or "").strip()
    for pattern, order in ((r"(\d{4})(\d{2})", "ym"),(r"(\d{4})[-/.](\d{1,2})", "ym"),(r"(\d{1,2})\.(\d{4})", "my")):
        m=re.fullmatch(pattern,s)
        if m:
            a,b=map(int,m.groups()); y,mo=(a,b) if order=="ym" else (b,a)
            if 1 <= mo <= 12: return y,mo
    return None

def _age_months(prod):
    from datetime import date
    return (date.today().year-prod[0])*12+(date.today().month-prod[1])

def _customs_personal(fields, rate, eur_rate):
    prod=_production_month(fields.get("production_date_raw") or fields.get("production_date"))
    if not prod: raise ValueError("Не удалось определить месяц и год производства; таможенный расчёт невозможен.")
    cc=_number(fields.get("engine_cc"), "объём двигателя (см³)")
    if cc <= 0: raise ValueError("Объём двигателя должен быть больше нуля.")
    age=_age_months(prod)
    if age < 0: raise ValueError("Дата производства находится в будущем.")
    if age <= 36:
        price_krw=_number(fields.get("price_krw"), "цена автомобиля в KRW")
        value_eur=(price_krw*rate/1000)/eur_rate
        if value_eur <= 8500: pct, minimum=.54,2.5
        elif value_eur <= 16700: pct, minimum=.48,3.5
        elif value_eur <= 42300: pct, minimum=.48,5.5
        elif value_eur <= 84500: pct, minimum=.48,7.5
        elif value_eur <= 169000: pct, minimum=.48,15.0
        else: pct, minimum=.48,20.0
        duty_eur=max(value_eur*pct,cc*minimum); age_label="до 3 лет"
    elif age <= 60:
        bands=[(1000,1.5),(1500,1.7),(1800,2.5),(2300,2.7),(3000,3.0),(float('inf'),3.6)]
        duty_eur=cc*next(rate for bound,rate in bands if cc<=bound); age_label="свыше 3 до 5 лет"
    else:
        bands=[(1000,3.0),(1500,3.2),(1800,3.5),(2300,4.8),(3000,5.0),(float('inf'),5.7)]
        duty_eur=cc*next(rate for bound,rate in bands if cc<=bound); age_label="старше 5 лет"
    return round(duty_eur*eur_rate),age_label,age

def calc_values(car_id, form):
    fields=parse(car_id)
    if fields.get("status") not in ("ready_for_manual_review",): raise ValueError(fields.get("error") or "Карточка не готова")
    # Use horsepower from Encar/XAPI (or an explicitly entered value) only; never invent 159 hp.
    manual_hp=(form.get("power_hp") or "").strip()
    if manual_hp:
        hp_value=_number(manual_hp, "мощность двигателя (л.с.)")
        if hp_value <= 0 or hp_value > 2000:
            raise ValueError("Мощность должна быть в диапазоне от 1 до 2000 л.с.")
        fields["power_hp"]=hp_value
        fields["power_hp_source"]="введено оператором"
    # Allow operator to confirm month/year when Encar API exposes only a year.
    production_month=(form.get("production_month") or "").strip()
    if production_month:
        if not re.fullmatch(r"(0[1-9]|1[0-2])\.\d{4}", production_month):
            raise ValueError("Месяц производства укажи в формате MM.YYYY, например 02.2021")
        fields["production_date_raw"]=production_month
        fields["production_date"]=production_month
        fields["production_date_source"]="введено и подтверждено оператором"
    manual_fuel=(form.get("manual_fuel") or "").strip()
    manual_transmission=(form.get("manual_transmission") or "").strip()
    if manual_fuel:
        fields["fuel"] = manual_fuel
        fields["fuel_source"] = "введено оператором"
    if manual_transmission:
        fields["transmission"] = manual_transmission
        fields["transmission_source"] = "введено оператором"
    fields["missing_fields"] = [k for k in fields.get("missing_fields", []) if not ((k == "fuel" and fields.get("fuel")) or (k == "transmission" and fields.get("transmission")))]
    rate=_number(form.get("rate","63.78"),"курс KRW/RUB")
    eur_rate=_number(form.get("eur_rate") or os.environ.get("EUR_RUB_RATE"),"курс EUR/RUB")
    kr_extra=_number(form.get("kr_extra","1740000"),"расходы в Корее")
    ru_extra=_number(form.get("ru_extra","450000"),"расходы в России")
    customs_adjustment=_number(form.get("customs_adjustment","0"),"корректировка таможни",True,0)
    manual_recycle=_number(form.get("manual_recycle"),"утильсбор",True,None)
    if rate<=0 or eur_rate<=0: raise ValueError("Курсы KRW/RUB и EUR/RUB должны быть больше нуля")
    customs_duty,age_label,age_months=_customs_personal(fields,rate,eur_rate)
    hp_raw=fields.get("power_hp")
    hp=_number(hp_raw,"мощность двигателя (л.с.)",allow_blank=True,default=None)
    if hp is not None and hp <= 160: recycle_fee=3400 if age_months <= 36 else 5200
    elif hp is not None and manual_recycle is not None: recycle_fee=manual_recycle
    elif hp is not None: recycle_fee=0
    else: recycle_fee=manual_recycle if manual_recycle is not None else 0
    krw_total=_number(fields.get("price_krw"),"цена автомобиля в KRW")+kr_extra
    raw_total=krw_total*rate/1000+customs_duty+customs_adjustment+recycle_fee+ru_extra
    total=int(math.ceil(raw_total/10000)*10000)
    warnings=["Предварительная оценка, не официальное таможенное решение. Для авто до 3 лет таможня может определить другую таможенную стоимость.","Проверь курсы EUR/RUB и KRW/RUB на дату оформления.","Льготный утильсбор 3 400/5 200 ₽ применяется только при соблюдении всех условий личного ввоза, включая своевременную регистрацию на плательщика."]
    if hp is not None and hp>160: warnings.append("Мощность выше 160 л.с.: льготный утильсбор не применяется. Укажи подтверждённую сумму коммерческого утильсбора; без неё публикация заблокирована.")
    if hp is None: warnings.append("Encar/XAPI не вернул мощность. Введи подтверждённую мощность вручную; расчёт не даёт разрешения на публикацию без неё.")
    if fields.get("missing_fields"): warnings.append("Не хватает обязательных характеристик: "+", ".join(fields["missing_fields"]))
    if fields.get("optional_missing_fields"): warnings.append("Не удалось определить дополнительные характеристики: "+", ".join(fields["optional_missing_fields"]))
    publishable=bool(fields.get("photos")) and not fields.get("missing_fields") and hp is not None and (hp<=160 or manual_recycle is not None)
    return fields,{"rate":rate,"eur_rate":eur_rate,"production_month":production_month,"customs_duty":customs_duty,"customs_adjustment":customs_adjustment,"recycle_fee":recycle_fee,"manual_recycle":manual_recycle,"kr_extra":kr_extra,"ru_extra":ru_extra,"krw_total":krw_total,"total":total,"age_label":age_label,"age_months":age_months,"warnings":warnings,"publishable":publishable,"power_hp":hp,"manual_fuel":manual_fuel,"manual_transmission":manual_transmission}

def make_post(fields, calc):
    # Telegram template: bold labels, trim after production date, clear separators.
    import html
    def esc(value):
        return html.escape(str(value if value not in (None, "") else "—"), quote=False)
    def fmt(v):
        try: return f"{float(v):,.0f}".replace(",", " ")
        except: return str(v or "—")
    try:
        raw_cc = str(fields.get("engine_cc") or "").strip().lower()
        if re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:l|литр(?:а|ов)?)", raw_cc):
            engine_l = f"{float(re.search(r'[0-9]+(?:[.,][0-9]+)?', raw_cc).group(0).replace(',', '.')):.1f}"
        else:
            cc_value = _number(raw_cc, "объём двигателя (см³)")
            engine_l = f"{cc_value / 1000:.1f}"
    except (TypeError, ValueError, AttributeError):
        engine_l = "—"
    power = ""
    if fields.get("power_hp"):
        try:
            hp = float(fields["power_hp"])
            power = f" / {int(hp) if hp.is_integer() else hp:g} л.с."
        except (TypeError, ValueError):
            power = f" / {fields['power_hp']} л.с."
    fuel = str(fields.get("fuel") or "").strip()
    transmission = str(fields.get("transmission") or "").strip()
    mileage = fmt(fields.get("mileage_km"))
    production = fields.get('production_date') or fields.get('year') or 'уточняется'
    trim = str(fields.get('trim') or '').strip()
    title = fields.get('title') or 'Автомобиль из Кореи'
    lines = [
        "🔥 АВТО ИЗ КОРЕИ 🇰🇷",
        "",
        f"🟡 <b>{esc(title)}</b>",
        "━━━━━━━━━━━━",
        f"✅ <b>Год выпуска:</b> {esc(production)}",
    ]
    if trim:
        lines.append(f"✅ <b>Комплектация:</b> {esc(trim)}")
    lines.append(f"✅ <b>Двигатель:</b> {esc(engine_l)} л{esc(power)}")
    if fuel: lines.append(f"✅ <b>Топливо:</b> {esc(fuel)}")
    if transmission: lines.append(f"✅ <b>КПП:</b> {esc(transmission)}")
    lines += [f"✅ <b>Пробег:</b> {esc(mileage)} км",
              "━━━━━━━━━━━━",
              "💰 СТОИМОСТЬ ДО МОСКВЫ", f"<b>{fmt(calc['total'])} ₽</b>",
              "━━━━━━━━━━━━",
              "🤝 Подберём и привезём автомобиль из Кореи и Японии под ваш бюджет!",
              "",
              "📲 +7(928)404 20 20 — Арсен",
              "",
              "Корея 🇰🇷 | Япония 🇯🇵 | Китай 🇨🇳"]
    return "\n".join(lines)

@app.route("/calculate", methods=["POST"])
def calculate():
    car_id=request.form.get("car_id","")
    try:
        fields,calc=calc_values(car_id,request.form)
        return render_template_string(HTML,car=car_id,data=fields,data_json="",calc=calc,default_rate=calc["rate"],default_eur_rate=calc["eur_rate"])
    except Exception as e:
        return f"Расчёт не выполнен: {str(e)}. Вернись назад и проверь введённые данные.",400

@app.route("/publish", methods=["POST"])
def publish():
    car_id=request.form.get("car_id","")
    try:
        fields,calc=calc_values(car_id,request.form)
        if not calc.get("publishable"): return "Публикация заблокирована: проверь недостающие характеристики и утильсбор.",400
        telegram_send(fields,calc)
        return "<html lang=ru><meta name=viewport content='width=device-width,initial-scale=1'><body style='background:#111;color:#eee;font:18px system-ui;padding:20px'><h2>Публикация отправлена в Telegram</h2><a style='color:#9ecbff' href='/'>Вернуться к парсеру</a></body></html>"
    except Exception as e:return f"Публикация не выполнена: {str(e)[:250]}",400

@app.route("/api/parse")
def api_parse():
    cid=getid(request.args.get("id") or request.args.get("url") or "")
    if not cid:return jsonify({"status":"failed","error":"Use ?id=41792916"}),400
    return jsonify(parse(cid))
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.environ.get("PORT","3000")))
