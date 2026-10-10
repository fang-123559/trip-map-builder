# -*- coding: utf-8 -*-
"""通用运行时回归探针 —— 与目的地无关。

期望值全部从页面内嵌的 SPOTS 数据推导，不写死条目数，
因此任何由本引擎生成的页面都能直接跑（换城市无需改脚本）。

覆盖四组：
  口径  A1-A5  卡片数/统计栏/地图图层/图例（对照 SPOTS 推导值）
  结构  B1-B4  清单在滚动区、说明块位置、复制按钮齐全、初始为占位态
  折叠  C1-C8  把手可用、收起隐藏地图、空间让渡、展开复原、invalidateSize、瓦片渲染
  交互  D1-D7  圆点开关、卡片开关、空白关闭、✕ 关闭、Esc 关闭、几何合理性

用法：
  python probe.py --html <页面.html> [--wide 1440] [--narrow 430]
"""
import argparse
import json
import os
import re
import subprocess
import sys

CHROME = next((p for p in [
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
] if os.path.exists(p)), "chrome")

PROBE = r"""
<script>
window.addEventListener('load',function(){
 setTimeout(function(){
  var out=[], fail=0;
  function ok(n,c,d){ out.push({t:n,p:!!c,d:String(d==null?'':d)}); if(!c) fail++; }
  function clickAt(node,x,y){
    if(!node) return false;
    if(x==null){ var r=node.getBoundingClientRect(); x=r.left+r.width/2; y=r.top+r.height/2; }
    node.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,clientX:x,clientY:y,view:window}));
    node.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,clientX:x,clientY:y,view:window}));
    return true;
  }
  function cards(){ return document.querySelectorAll('#list .card'); }
  function vis(n){ return !!n && n.offsetHeight>0 && n.offsetWidth>0 && getComputedStyle(n).display!=='none'; }
  function H(n){ return n? n.getBoundingClientRect().height : -1; }
  function opened(){ return !!document.querySelector('#detail .dhead'); }
  function title(){ var h=document.querySelector('#detail .dhead h3'); return h? h.textContent.trim() : null; }
  function sz(){ try{ var s=MAP.getSize(); return {w:s.x,h:s.y}; }catch(e){ return {w:-1,h:-1}; } }

  /* ---------- 期望值：全部由页面数据推导 ---------- */
  var exp = {
    total : SPOTS.length,
    exact : SPOTS.filter(function(s){return s.lat && s.loc!=='approx' && !s.offmap;}).length,
    approx: SPOTS.filter(function(s){return s.loc==='approx';}).length,
    noloc : SPOTS.filter(function(s){return !s.lat;}).length,
    /* 圆点只统计 circleMarker：星标条目渲染为图标(divIcon)，不计入 path */
    pts   : SPOTS.filter(function(s){return s.lat && !s.offmap && !s.star;}).length,
    stars : SPOTS.filter(function(s){return s.star;}).length
  };
  var narrow = window.innerWidth <= 1080;
  var tag = narrow ? 'N' : 'W';

  var bar=document.getElementById('mapToggle'), mp=document.getElementById('map');
  var box=document.querySelector('.map-main'), lg=document.querySelector('.map-main .legend');
  var pane=document.getElementById('pane'), list=document.getElementById('list');
  var aside=document.querySelector('.grid2 > aside'), grid=document.querySelector('.grid2');

  /* ---------- A 口径 ---------- */
  ok(tag+'A1 卡片数 = 数据条目数', cards().length===exp.total, cards().length+' vs '+exp.total);
  ok(tag+'A1 统计栏与推导值一致',
     document.getElementById('s1').textContent===String(exp.total)
     && document.getElementById('s2').textContent===String(exp.exact)
     && document.getElementById('s3').textContent===String(exp.noloc)
     && document.getElementById('s5').textContent===String(exp.approx),
     's1='+document.getElementById('s1').textContent+' s2='+document.getElementById('s2').textContent
     +' s5='+document.getElementById('s5').textContent+' s3='+document.getElementById('s3').textContent
     +' | 期望 '+exp.total+'/'+exp.exact+'/'+exp.approx+'/'+exp.noloc);
  ok(tag+'A2 地图圆点数 = 可标注条目数（不含星标图钉）',
     document.querySelectorAll('#map path.leaflet-interactive').length===exp.pts,
     document.querySelectorAll('#map path.leaflet-interactive').length+' vs '+exp.pts);
  ok(tag+'A3 星标图层数 = 星标条目数',
     document.querySelectorAll('#map .leaflet-marker-icon').length===exp.stars,
     document.querySelectorAll('#map .leaflet-marker-icon').length+' vs '+exp.stars);
  ok(tag+'A4 图例非空', (document.getElementById('legend').textContent||'').trim().length>0,
     'len='+(document.getElementById('legend').textContent||'').length);
  /* 不能按颜色值判断（有分组本身就配色为灰），必须查 CFG.typeColor 是否显式收录。
     旧版页面没有 CFG，此项自动跳过（用于新旧对照）。 */
  var tc = (typeof CFG!=='undefined' && CFG.typeColor) ? CFG.typeColor : null;
  var usedTy = Object.keys(SPOTS.reduce(function(m,s){ m[s.ty]=1; return m; }, {}));
  var badTy = tc ? usedTy.filter(function(t){ return !(t in tc); }) : [];
  ok(tag+'A5 每个类别都在配置中被显式配色', tc ? badTy.length===0 : true,
     tc ? (badTy.length ? ('未归类 '+badTy.length+' 项: '+badTy.join('、'))
                        : ('已收录 '+Object.keys(tc).length+' 项'))
        : '页面无 CFG（旧版），跳过');

  /* ---------- B 结构 ---------- */
  ok(tag+'B1 清单在独立滚动区内', !!pane && !!list && pane.contains(list));
  ok(tag+'B2 每张卡片都有复制按钮',
     document.querySelectorAll('#list .card .cp').length===cards().length,
     document.querySelectorAll('#list .card .cp').length+' vs '+cards().length);
  ok(tag+'B3 初始为占位态（未自动打开详情）', !opened());
  ok(tag+'B4 说明块在滚动区内', document.querySelectorAll('#pane > .notes').length>=1,
     'notes='+document.querySelectorAll('#pane > .notes').length);

  /* ---------- C 折叠 ---------- */
  ok(tag+'C1 折叠把手存在且可见', vis(bar), bar?getComputedStyle(bar).display:'null');
  var h0=H(mp), asideH0=H(aside);
  ok(tag+'C2 初始为展开态', !box.classList.contains('collapsed') && h0>150, 'map高='+h0.toFixed(0));
  clickAt(bar);
  ok(tag+'C3 点把手后进入折叠态', box.classList.contains('collapsed'));
  ok(tag+'C3 折叠后地图不再占位', !vis(mp), 'map display='+getComputedStyle(mp).display);
  ok(tag+'C4 折叠后图例一并隐藏', !vis(lg), 'legend h='+H(lg).toFixed(0));
  ok(tag+'C5 地图区塌陷（留给清单）', H(box)<110, 'mapbox高='+H(box).toFixed(0));
  ok(tag+'C6 把手文案与 aria 同步', bar.getAttribute('aria-expanded')==='false',
     'aria='+bar.getAttribute('aria-expanded')+' 文案='+document.getElementById('mpArrow').textContent);
  if(!narrow){ ok(tag+'C6 宽屏折叠后切单列并限宽',
     grid.classList.contains('mapcollapsed') && getComputedStyle(aside).maxWidth==='980px',
     'class='+grid.className+' maxW='+getComputedStyle(aside).maxWidth); }
  /* 折叠态下功能必须仍可用 */
  clickAt(cards()[0]);
  ok(tag+'C7 折叠态下点卡片仍能打开详情', opened(), 'opened='+opened());
  clickAt(cards()[0]);
  clickAt(bar);
  ok(tag+'C8 再点把手恢复展开', !box.classList.contains('collapsed') && H(mp)>150,
     'map高='+H(mp).toFixed(0));
  var s2=sz();
  ok(tag+'C8 展开后 Leaflet 尺寸与容器一致',
     Math.abs(s2.w-mp.clientWidth)<2 && Math.abs(s2.h-mp.clientHeight)<2,
     'getSize='+s2.w.toFixed(0)+'x'+s2.h.toFixed(0)+' client='+mp.clientWidth+'x'+mp.clientHeight);
  ok(tag+'C8 展开后瓦片已实际渲染',
     document.querySelectorAll('#map .leaflet-tile-loaded').length>0,
     'tiles='+document.querySelectorAll('#map .leaflet-tile-loaded').length);

  /* ---------- D 打开/关闭闭环 ---------- */
  clickAt(cards()[0]);
  ok(tag+'D1 点卡片打开详情', opened(), 'title='+title());
  var n1=title();
  clickAt(cards()[0]);
  ok(tag+'D2 再点同一张卡片关闭', !opened(), 'opened='+opened());
  /* 圆点：真实事件路径 */
  var dot=document.querySelector('#map path.leaflet-interactive');
  clickAt(dot);
  ok(tag+'D3 点地图圆点打开详情', opened(), 'opened='+opened());
  var dot2=document.querySelector('#map path[stroke="#22201d"]') || dot;
  clickAt(dot2);
  ok(tag+'D4 再点同一圆点关闭', !opened(), 'opened='+opened());
  /* 空白处关闭：用 elementFromPoint 取真实背景元素，避免绕过真实事件路径 */
  clickAt(cards()[0]);
  var r=mp.getBoundingClientRect();
  var el0=document.elementFromPoint(r.left+r.width-6, r.top+6);
  clickAt(el0, r.left+r.width-6, r.top+6);
  ok(tag+'D5 点地图空白处关闭', !opened(), 'opened='+opened()+' hit='+(el0?el0.className||el0.tagName:'null'));
  /* ✕ 按钮 */
  clickAt(cards()[0]);
  var dx=document.getElementById('dclose');
  var dr=dx?dx.getBoundingClientRect():null, pr=document.getElementById('detail').getBoundingClientRect();
  ok(tag+'D6 关闭按钮几何合理（可见且在面板内）',
     !!dx && dr.width>0 && dr.height>0 && dr.right<=pr.right+1 && dr.left>=pr.left-1,
     dx?('dx='+dr.width.toFixed(0)+'x'+dr.height.toFixed(0)+' panelRight='+pr.right.toFixed(0)):'null');
  clickAt(dx);
  ok(tag+'D6 点 ✕ 关闭详情', !opened(), 'opened='+opened());
  /* Esc */
  clickAt(cards()[0]);
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  ok(tag+'D7 Esc 关闭详情', !opened(), 'opened='+opened());

  document.title='PROBE'+JSON.stringify({fail:fail,total:out.length,res:out});
 }, 500);
}, {once:true});
</script>
"""


def run(html_path, w, h, budget=14000):
    src = open(html_path, encoding="utf-8").read()
    tmp = os.path.join(os.path.dirname(os.path.abspath(html_path)), "_probe_tmp.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src.replace("</body>", PROBE + "</body>"))
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--window-size=%d,%d" % (w, h), "--virtual-time-budget=%d" % budget,
           "--dump-dom", "file:///" + tmp.replace("\\", "/")]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        os.remove(tmp)
    except OSError:
        pass
    m = re.search(r"<title>PROBE(.*?)</title>", p.stdout, re.S)
    if not m:
        return {"error": "no probe result", "stderr": (p.stderr or "")[-600:]}
    return json.loads(m.group(1))


def main():
    ap = argparse.ArgumentParser(description="通用运行时回归探针")
    ap.add_argument("--html", required=True)
    ap.add_argument("--wide", type=int, default=1440)
    ap.add_argument("--narrow", type=int, default=430)
    ap.add_argument("--only", choices=["wide", "narrow"], help="只跑单档")
    a = ap.parse_args()
    html = os.path.abspath(a.html)
    if not os.path.exists(html):
        print("找不到页面：%s" % html, file=sys.stderr)
        sys.exit(2)

    viewports = [(a.wide, 900, "宽屏"), (a.narrow, 900, "窄屏")]
    if a.only == "wide":
        viewports = viewports[:1]
    elif a.only == "narrow":
        viewports = viewports[1:]

    total_fail = 0
    for (w, h, name) in viewports:
        print("=== %s %dx%d ===" % (name, w, h))
        r = run(html, w, h, 6000 if name == "窄屏" else 14000)
        if "error" in r:
            print("  ERROR:", r)
            total_fail += 1
            continue
        for it in r["res"]:
            print("  [%s] %s%s" % ("PASS" if it["p"] else "FAIL", it["t"],
                                   "" if it["p"] else "\n        → " + it["d"]))
        print("  -- 失败 %d / 共 %d --" % (r["fail"], r["total"]))
        total_fail += r["fail"]
    print("\nTOTAL FAIL = %d" % total_fail)
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
