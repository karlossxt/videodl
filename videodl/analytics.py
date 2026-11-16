"""Terceros que se cargan en el <head>: Google Tag Manager y Adcash.

GTM se activa con ``GTM_ID``; Adcash con ``ACLIB_ZONE_ID`` y ``ACLIB_MODE``. Si
la variable está vacía no se inyecta nada y la CSP no cambia.
"""

from __future__ import annotations

import base64
import hashlib

from .config import ACLIB_MODE, ACLIB_ZONE_ID, GTM_ID

_GTM_HOST = "https://www.googletagmanager.com"


def gtm_inline_script(gtm_id: str = GTM_ID) -> str:
    """Cargador oficial de GTM (contenido estable → se puede fijar con hash CSP)."""
    if not gtm_id:
        return ""
    return (
        "(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':"
        "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],"
        "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src="
        f"'{_GTM_HOST}/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);"
        f"}})(window,document,'script','dataLayer','{gtm_id}');"
    )


def gtm_head_html(gtm_id: str = GTM_ID) -> str:
    script = gtm_inline_script(gtm_id)
    return f"  <script>{script}</script>" if script else ""


def aclib_head_html(zone_id: str = ACLIB_ZONE_ID, mode: str = ACLIB_MODE) -> str:
    """Config de Adcash y aviso de consentimiento (``consent.js``).

    La librería no se emite en el HTML: ``consent.js`` la inyecta solo cuando la
    persona acepta, para no cargar publicidad antes del consentimiento. El
    cargador por sí solo tampoco muestra nada: necesita ``runAutoTag`` (anuncios
    dentro de la página) o ``runPop`` (pop-under) con el ``zoneId`` del panel.
    """
    if not zone_id:
        return ""
    call = "runPop" if mode == "pop" else "runAutoTag"
    payload = f'{{ zoneId: "{zone_id}", call: "{call}" }}'
    return (
        f"  <script>window.__aclib = {payload};</script>\n"
        '  <script src="/consent.js"></script>'
    )


def gtm_noscript_html(gtm_id: str = GTM_ID) -> str:
    """<noscript> de GTM: va justo después de <body> (visitantes sin JavaScript)."""
    if not gtm_id:
        return ""
    return (
        f'<noscript><iframe src="{_GTM_HOST}/ns.html?id={gtm_id}" height="0" width="0" '
        'style="display:none;visibility:hidden" title="Google Tag Manager"></iframe></noscript>\n'
    )


def _add_sources(csp: str, directive: str, sources: list[str]) -> str:
    parts = csp.split(";")
    for index, part in enumerate(parts):
        fields = part.strip().split()
        if fields and fields[0].lower() == directive:
            missing = [src for src in sources if src not in fields]
            parts[index] = " ".join([*fields, *missing])
            return ";".join(parts)
    return csp


def csp_with_gtm(csp: str, gtm_id: str = GTM_ID) -> str:
    """Permite el cargador de GTM y las peticiones de Google Analytics."""
    script = gtm_inline_script(gtm_id)
    if not csp or not script:
        return csp
    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = _add_sources(csp, "script-src", [f"'sha256-{digest}'", _GTM_HOST])
    csp = _add_sources(
        csp,
        "connect-src",
        [
            _GTM_HOST,
            "https://*.google-analytics.com",
            "https://*.analytics.google.com",
            "https://*.googletagmanager.com",
        ],
    )
    if "frame-src" in csp:
        return _add_sources(csp, "frame-src", [_GTM_HOST])
    # Sin frame-src, default-src 'self' bloquearía el iframe del <noscript>.
    return f"{csp.rstrip().rstrip(';')}; frame-src 'self' {_GTM_HOST}"

def csp_with_nonce(csp: str, nonce: str) -> str:
    """Adapta la CSP por respuesta a los scripts de terceros y les pone nonce.

    Las redes publicitarias cambian de dominios con frecuencia, así que se usa
    una CSP basada en nonce: el nonce autoriza los scripts presentes en el HTML y
    strict-dynamic permite que esos scripts carguen sus dependencias de confianza.
    """
    if not csp or not nonce:
        return csp
    csp = _add_sources(
        csp,
        "script-src",
        [
            f"'nonce-{nonce}'",
            "'strict-dynamic'",
            "'unsafe-inline'",
            "'unsafe-eval'",
            "https:",
            "http:",
        ],
    )
    csp = _add_sources(csp, "connect-src", ["https:"])
    # Algunas unidades de Adcash se pintan dentro de la página (shadow DOM) y
    # piden creatividades de vídeo desde su CDN; si no, el navegador las bloquea.
    csp = _add_sources(csp, "media-src", ["https:"])
    # Las librerías publicitarias crean workers desde blob: (aclib.js lo hace).
    csp = _add_sources(csp, "worker-src", ["blob:"])
    if "frame-src" in csp:
        return _add_sources(csp, "frame-src", ["https:"])
    return f"{csp.rstrip().rstrip(';')}; frame-src 'self' https:"

