// Normaliza el `detail` de un error de la API a texto. En un 422 de FastAPI/Pydantic el
// `detail` es un arreglo de objetos {type, loc, msg, input, ctx}; pasarlo tal cual a
// message.error o a un nodo de React lo revienta (error #31). Aquí se reduce a los `msg`.
export function formatApiError(err, fallback = 'Ocurrió un error') {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
        const msgs = detail.map((d) => d && d.msg).filter(Boolean);
        if (msgs.length) return msgs.join('. ');
    }
    return fallback;
}
