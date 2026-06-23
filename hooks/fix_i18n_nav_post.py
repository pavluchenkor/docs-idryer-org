# POST (priority -200): вкладываем фантомные fallback-секции (default-язык),
# оставшиеся на верхнем уровне после i18n, в одноимённые локализованные секции.
# Сопоставление — по сегменту нормализованного пути на каждом уровне вложенности.
from mkdocs.plugins import event_priority

def _children(x): return getattr(x,'children',None) or []
def _file(x): return getattr(x,'file',None)
def _is_section(x): return getattr(x,'is_section',False)

def _first_norm(item):
    f=_file(item)
    if f is not None: return getattr(f,'norm_src_uri',None) or f.src_uri
    for c in _children(item):
        n=_first_norm(c)
        if n: return n
    return None

def _all_locales(item, acc):
    f=_file(item)
    if f is not None:
        loc=getattr(f,'localization',None)
        if loc: acc.add(loc)
    for c in _children(item): _all_locales(c,acc)
    return acc

def _key(item, depth):
    """page -> полный норм-путь; section -> префикс пути до своего уровня."""
    f=_file(item)
    n=_first_norm(item)
    if n is None: return None
    if f is not None: return n           # страница
    return '/'.join(n.split('/')[:depth+1])

def _merge(loc_children, fb_children, depth):
    by={}
    for x in loc_children: by.setdefault(_key(x,depth), x)
    for f in fb_children:
        k=_key(f,depth); l=by.get(k)
        if l is not None and _is_section(l) and _is_section(f):
            l.children=_merge(_children(l), _children(f), depth+1)
        elif l is None:
            loc_children.append(f); by[k]=f
    return loc_children

@event_priority(-200)
def on_nav(nav, config, files):
    i18n=config['plugins'].get('i18n')
    if i18n is None: return nav
    cur=getattr(i18n,'current_language',None)
    dft=getattr(i18n,'default_language',None)
    if not cur or cur==dft: return nav
    phantoms=[it for it in nav.items
              if _is_section(it) and _all_locales(it,set())=={dft}]
    if not phantoms: return nav
    localized=[it for it in nav.items if it not in phantoms]
    by={}
    for x in localized: by.setdefault(_key(x,0), x)
    keep=list(localized)
    for ph in phantoms:
        l=by.get(_key(ph,0))
        if l is not None and _is_section(l):
            l.children=_merge(_children(l), _children(ph), 1)
        else:
            keep.append(ph)
    nav.items=keep
    return nav
