"""Motor de ingesta cognitiva: documentos -> filas.

Nucleo agnostico al modulo. Cada modulo declara sus entidades destino en
`contracts.py` y el motor se encarga de lo dificil: leer el documento sin
aplastar su estructura, descomponerlo en unidades, reconciliar contra lo que ya
existe, resolver contradicciones entre documentos y dejar todo reversible.

Reparto de responsabilidades — la IA propone, el codigo decide:

    reader        extrae estructura (hojas, bloques, tablas, secciones)
    comprehension la IA lee y produce un mapa de volcado (que unidades hay y
                  como se descomponen). Es lo unico que hace un LLM.
    reconciler    crear o enlazar: determinista, por clave natural y similitud
    conflicts     dos documentos discrepan: gana el mas restrictivo, y el valor
                  descartado queda registrado con su fuente
    materializer  ejecuta el mapa contra la base de datos
    batch         lote, rastro por registro, deshacer y forzar

BCP es el primer consumidor (`bcp_targets.py`); enchufar otro modulo es
declarar sus `EntitySpec`, no tocar el motor.
"""
