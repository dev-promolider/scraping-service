# Tipos de cambio de referencia (moneda -> USD). Se usan para no dejar que el
# LLM "adivine" el tipo de cambio; si aparece una moneda no listada aqui, el
# precio se deja tal cual en su moneda original.
TASAS_A_USD = {
    "PEN": 1 / 3.3949,
    "BRL": 1 / 5.0769,
}


def convertir_a_usd(precio: float, moneda: str) -> float | None:
    moneda = (moneda or "").upper()
    if moneda == "USD":
        return round(precio, 2)
    if moneda in TASAS_A_USD:
        return round(precio * TASAS_A_USD[moneda], 2)
    return None  # moneda no soportada por este conversor
