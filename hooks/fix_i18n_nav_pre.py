# PRE-i18n (priority 100): переименовать обёртку текущего языка так, чтобы
# reconfigure_navigation плагина (сравнение по locale.capitalize()) её развернул.
# Нужно для региональных локалей (pt-BR, zh-Hant), где dirname_to_title != capitalize().
from mkdocs.plugins import event_priority

def _is_section(x): return getattr(x,'is_section',False)
def _descend_locale(item):
    f=getattr(item,'file',None)
    if f is not None: return getattr(f,'localization',None)
    for c in (getattr(item,'children',None) or []):
        loc=_descend_locale(c)
        if loc: return loc
    return None

@event_priority(100)
def on_nav(nav, config, files):
    i18n=config['plugins'].get('i18n')
    if i18n is None: return nav
    cur=getattr(i18n,'current_language',None)
    if not cur: return nav
    for it in nav.items:
        if _is_section(it) and _descend_locale(it)==cur:
            it.title=cur.capitalize()
            break
    return nav
