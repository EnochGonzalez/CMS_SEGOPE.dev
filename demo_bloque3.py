"""Recorrido de demostración del Bloque 3 contra la API ya encendida (certificados, catálogo, perfil y archivos).

Uso (con la API corriendo en otra terminal):
    python demo_bloque3.py

Sube un PDF y una imagen de ejemplo, crea un certificado con ellos, lo edita y lo elimina; prueba los errores
principales; crea, edita y elimina un elemento del catálogo; y guarda el perfil sin cambiar su contenido.
Los archivos subidos quedan en la carpeta uploads/ (borrar un certificado no borra sus archivos).
"""
import base64
import getpass
import os
import uuid

import httpx

BASE = os.getenv("CMS_URL", "http://localhost:8000")
PDF_EJEMPLO = (b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
               b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
PNG_EJEMPLO = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def mostrar(titulo, r):
    print(f"\n{titulo}")
    cuerpo = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
    if cuerpo and cuerpo.get("status") == "error":
        detalle = "; ".join(f"{d['field']}: {d['issue']}" for d in cuerpo["details"])
        print(f"   HTTP {r.status_code}  {cuerpo['code']}  {detalle}".rstrip())
    elif cuerpo:
        print(f"   HTTP {r.status_code}  {cuerpo['message']}")
    else:
        print(f"   HTTP {r.status_code}  ({r.headers.get('content-type')}, {len(r.content)} bytes)")
    return cuerpo


def clave():
    return str(uuid.uuid4())


def main():
    api = httpx.Client(base_url=BASE, timeout=15)
    correo = os.getenv("CMS_EMAIL") or input("Correo del administrador: ").strip()
    password = os.getenv("CMS_PASSWORD") or getpass.getpass("Contraseña: ")

    r = api.post("/api/v1/auth/login", json={"email": correo, "password": password})
    cuerpo = mostrar("1. Login", r)
    if r.status_code != 200:
        return
    auth = {"Authorization": f"Bearer {cuerpo['data']['access_token']}"}

    def subir(contenido, nombre, proposito):
        return api.post("/api/v1/files", headers={**auth, "Idempotency-Key": clave()}, data={"purpose": proposito}, files={"file": (nombre, contenido)})

    # ---------------------------------------------------------------- archivos
    r = subir(PDF_EJEMPLO, "constancia.pdf", "CERTIFICATE_PDF")
    url_pdf = mostrar("2. Subir un PDF", r)["data"]["url"]
    url_img = mostrar("3. Subir una imagen PNG", subir(PNG_EJEMPLO, "constancia.png", "CERTIFICATE_IMAGE"))["data"]["url"]
    print(f"   url del PDF: {url_pdf}")
    mostrar("4. Abrir esa URL (la API sirve los archivos en /media)", httpx.get(url_pdf))
    mostrar("5. Subir un archivo de texto como si fuera PDF", subir(b"hola, esto no es un PDF", "falso.pdf", "CERTIFICATE_PDF"))
    mostrar("6. Subir un PDF con el propósito de un logo", subir(PDF_EJEMPLO, "constancia.pdf", "STACK_LOGO"))

    # ---------------------------------------------------------------- certificados
    cert = {"title": "Certificado de demostración", "issuer": "Institución de ejemplo", "issued_at": "2026-10-24",
            "pdf_url": url_pdf, "image_url": url_img}
    r = api.post("/api/v1/certificates", headers={**auth, "Idempotency-Key": clave()}, json=cert)
    cid = mostrar("7. Crear un certificado con esas URLs", r)["data"]["certificate_id"]
    publicos = httpx.get(f"{BASE}/api/v1/public/certificates").json()["data"]["items"]
    print(f"   Certificados públicos ahora: {len(publicos)}  (el más reciente: {publicos[0]['title']})")
    mostrar("8. Crear uno con una URL de otro sitio", api.post("/api/v1/certificates", headers={**auth, "Idempotency-Key": clave()},
            json={**cert, "title": "Otro", "pdf_url": "https://otro-sitio.com/a.pdf"}))
    mostrar("9. Editar el certificado (PUT)", api.put(f"/api/v1/certificates/{cid}", headers=auth, json={**cert, "title": "Título corregido"}))
    mostrar("10. Eliminar el certificado", api.delete(f"/api/v1/certificates/{cid}", headers=auth))
    print(f"    Certificados públicos después: {len(httpx.get(f'{BASE}/api/v1/public/certificates').json()['data']['items'])}")

    # ---------------------------------------------------------------- catálogo
    r = api.post("/api/v1/tech-stack", headers={**auth, "Idempotency-Key": clave()}, json={"name": "Tecnología de demostración", "category": "HERRAMIENTA"})
    cuerpo = mostrar("11. Crear un elemento del catálogo (queda al final)", r)
    sid = cuerpo["data"]["stack_id"]
    print(f"    display_order asignado: {cuerpo['data']['display_order']}")
    mostrar("12. Editarlo (PUT)", api.put(f"/api/v1/tech-stack/{sid}", headers=auth,
            json={"name": "Tecnología editada", "category": "NUBE", "show_in_profile": False}))
    java = next(i["stack_id"] for i in httpx.get(f"{BASE}/api/v1/public/tech-stack", params={"limit": 50}).json()["data"]["items"] if i["name"] == "Java")
    mostrar("13. Intentar eliminar Java (lo usan proyectos)", api.delete(f"/api/v1/tech-stack/{java}", headers=auth))
    mostrar("14. Eliminar el elemento de demostración", api.delete(f"/api/v1/tech-stack/{sid}", headers=auth))

    # ---------------------------------------------------------------- perfil
    perfil = httpx.get(f"{BASE}/api/v1/public/profile").json()["data"]
    cuerpo_perfil = {k: v for k, v in perfil.items() if k not in ("profile_id", "updated_at") and v is not None}
    mostrar("15. Guardar el perfil sin cambiar su contenido (PUT)", api.put("/api/v1/profile", headers=auth, json=cuerpo_perfil))
    mostrar("16. Intentar eliminar el perfil", api.delete("/api/v1/profile", headers=auth))
    print("\nListo.")


if __name__ == "__main__":
    main()
