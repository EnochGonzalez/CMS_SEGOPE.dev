"""Recorrido de demostración del Bloque 2 contra la API ya encendida (como la prueba con HTTPX de tu práctica).

Uso (con la API corriendo en otra terminal):
    python demo_bloque2.py

Hace: login -> crea un borrador -> intenta publicarlo incompleto (422) -> lo completa -> lo publica ->
repite la publicación con la misma Idempotency-Key -> lo archiva. Usa un slug nuevo en cada ejecución;
los proyectos archivados no se pueden borrar, así que quedan en la base (se limpian con  python -m app.seed --reset).
"""
import getpass
import os
import time
import uuid

import httpx

BASE = os.getenv("CMS_URL", "http://localhost:8000")
PUBLICO = f"{BASE}/api/v1/public/projects"


def mostrar(titulo, r):
    print(f"\n{titulo}")
    cuerpo = r.json() if r.content else None
    if cuerpo and cuerpo.get("status") == "error":
        detalle = "; ".join(f"{d['field']}: {d['issue']}" for d in cuerpo["details"])
        print(f"   HTTP {r.status_code}  {cuerpo['code']}  {detalle}".rstrip())
    elif cuerpo:
        print(f"   HTTP {r.status_code}  {cuerpo['message']}")
    else:
        print(f"   HTTP {r.status_code}  (sin cuerpo)")
    return cuerpo


def main():
    cliente = httpx.Client(base_url=BASE, timeout=15)
    correo = os.getenv("CMS_EMAIL") or input("Correo del administrador: ").strip()
    clave = os.getenv("CMS_PASSWORD") or getpass.getpass("Contraseña: ")

    mostrar("1. Sin token no se puede administrar", cliente.get("/api/v1/projects"))

    r = cliente.post("/api/v1/auth/login", json={"email": correo, "password": clave})
    cuerpo = mostrar("2. Login", r)
    if r.status_code != 200:
        return
    cabeceras = {"Authorization": f"Bearer {cuerpo['data']['access_token']}"}

    slug = f"demo-{int(time.time())}"
    r = cliente.post("/api/v1/projects", headers={**cabeceras, "Idempotency-Key": str(uuid.uuid4())},
                     json={"title": "Proyecto de demostración", "slug": slug})
    cuerpo = mostrar("3. Crear un borrador solo con título y slug", r)
    pid = cuerpo["data"]["project_id"]

    clave_publicar = str(uuid.uuid4())
    r = cliente.post(f"/api/v1/projects/{pid}/publish", headers={**cabeceras, "Idempotency-Key": clave_publicar})
    mostrar("4. Intentar publicarlo incompleto (contrato de publicación)", r)

    lenguajes = cliente.get("/api/v1/public/tech-stack", params={"category": "LENGUAJE"}).json()["data"]["items"]
    r = cliente.put(f"/api/v1/projects/{pid}", headers=cabeceras, json={
        "title": "Proyecto de demostración", "slug": slug, "is_featured": False,
        "short_description": "Resumen corto que se verá en la tarjeta del blog.",
        "description": "Descripción más larga del proyecto de demostración del CMS.",
        "project_date": "2026-10-24", "stack_ids": [lenguajes[0]["stack_id"]], "tags": ["Demo"],
    })
    mostrar("5. Completarlo con PUT", r)

    r = cliente.post(f"/api/v1/projects/{pid}/publish", headers={**cabeceras, "Idempotency-Key": clave_publicar})
    mostrar("6. Publicarlo", r)
    print(f"   recompilation_triggered = {r.json()['data']['recompilation_triggered']}  (será true cuando se conecte el pipeline, Bloque 4)")

    r = cliente.post(f"/api/v1/projects/{pid}/publish", headers={**cabeceras, "Idempotency-Key": clave_publicar})
    mostrar("7. Repetir la publicación con la MISMA Idempotency-Key (reintento)", r)
    print(f"   Idempotent-Replayed = {r.headers.get('idempotent-replayed')}  (la respuesta original, sin publicar dos veces)")

    r = cliente.post(f"/api/v1/projects/{pid}/publish", headers={**cabeceras, "Idempotency-Key": str(uuid.uuid4())})
    mostrar("8. Publicar otra vez con una clave NUEVA", r)

    slugs = [p["slug"] for p in httpx.get(PUBLICO).json()["data"]["items"]]
    print(f"\n9. Lecturas públicas ahora: {slugs}")

    r = cliente.post(f"/api/v1/projects/{pid}/archive", headers={**cabeceras, "Idempotency-Key": str(uuid.uuid4())})
    mostrar("10. Archivarlo (deja de verse en el blog)", r)
    slugs = [p["slug"] for p in httpx.get(PUBLICO).json()["data"]["items"]]
    print(f"    Lecturas públicas después: {slugs}")

    r = cliente.delete(f"/api/v1/projects/{pid}", headers=cabeceras)
    mostrar("11. Intentar eliminarlo (los archivados no se borran)", r)
    print("\nListo.")


if __name__ == "__main__":
    main()
