# Seguridad del pipeline

## Datos sensibles identificados

Dentro del proyecto se identificaron tres elementos que deben protegerse:

* **user_id** y **source_user_id**: identificadores asociados a usuarios dentro del sistema.
* **FERNET_KEY**: clave usada para cifrar información sensible.
* **DATABASE_URL**: credencial de conexión a la base de datos en Supabase.

Estos datos no deberían quedar expuestos en el repositorio, en los logs ni en archivos públicos.

## Controles de seguridad que ya existen

Al revisar el código, se encontraron varias medidas positivas ya implementadas.

Primero, en `src/carga.py` se cifra la información de `user_id` y `source_user_id` antes de cargarla en la tabla `notificaciones`. Para esto se usa Fernet. Después del cifrado, las columnas originales en texto claro se eliminan con:

```python
df.drop(columns=["user_id", "source_user_id"])
```

Esto evita que los identificadores queden guardados directamente en la tabla final de notificaciones válidas.

También existe un control para los logs. En `src/seguridad.py` está la función `enmascarar()`, que oculta parte del identificador y deja visible solo la primera letra. Por ejemplo, un usuario podría mostrarse como `U***`. Esto ayuda a revisar procesos sin exponer datos completos.

Otro punto positivo es que los secretos no están versionados. El archivo `.gitignore` excluye `.env`, y el archivo `.env.example` solo contiene ejemplos o placeholders, no credenciales reales.

En Render, las variables sensibles como `FERNET_KEY` y `DATABASE_URL` se configuran desde el panel de entorno. Además, en `render.yaml` aparecen con `sync: false`, lo que significa que no se sincronizan ni quedan escritas en el archivo del repositorio.

El panel tampoco entrega los valores de las variables sensibles. El endpoint `/api/status` solo muestra si las variables están configuradas o no, usando valores tipo `true` o `false`.

Por último, el endpoint `/api/run` valida la etapa solicitada contra una lista blanca llamada `ETAPAS`. Esto es importante porque evita ejecutar comandos construidos libremente desde texto ingresado por el usuario.

## Hallazgos y riesgos detectados

| N° | Hallazgo                                                                                                                                                                                                                                              | Severidad                                              | Evidencia                                   | Mejora propuesta                                                           |
| -: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------- | -------------------------------------------------------------------------- |
|  1 | Los endpoints `/api/run` y `/api/reset` no tienen autenticación. Además, el servidor escucha en `0.0.0.0`, por lo que en Render queda expuesto mediante una URL pública. Esto permitiría que una persona externa ejecute el pipeline o haga un reset. | Alta                                                   | `server.py`, funciones `do_POST` y `main()` | Agregar un token de acceso. Deshabilitar `/api/reset` en producción.       |
|  2 | Los registros rechazados guardan `user_id` y `source_user_id` en texto claro.                                                                                                                                                                         | Media-alta si se usaran datos reales                   | `src/validacion.py`, líneas 239-263         | Eliminar esos campos antes de guardar el rechazo o cifrarlos.              |
|  3 | Los rechazados se acumulan entre corridas. En la revisión se observaron muchos registros acumulados antes de hacer reset.                                                                                                                             | Media                                                  | Conteos visibles en el panel de Render      | Limpiar la tabla entre demostraciones o definir una política de retención. |
|  4 | El contenedor Docker corre como usuario `root`.                                                                                                                                                                                                       | Media                                                  | `Dockerfile` sin instrucción `USER`         | Crear y usar un usuario no-root antes del `CMD`.                           |
|  5 | El rol de Supabase podría tener más permisos de los necesarios.                                                                                                                                                                                       | Media                                                  | Uso de `DATABASE_URL` con rol de Postgres   | Crear roles con permisos mínimos y activar Row Level Security.             |
|  6 | El archivo CSV de entrada queda incluido dentro de la imagen Docker.                                                                                                                                                                                  | Baja en este proyecto, porque los datos son sintéticos | `Dockerfile` usa `COPY data/`               | Con datos reales, montar el archivo desde fuera de la imagen.              |

## Propuesta para minimizar los rechazados

Para auditar una fila rechazada no es necesario guardar todos sus datos. En la mayoría de los casos basta con conservar:

* `notification_id`
* `motivo_rechazo`
* etapa del pipeline
* fecha del rechazo

Por eso, la mejora recomendada es eliminar `user_id` y `source_user_id` antes de insertar registros en la tabla `rechazados` y antes de escribir el CSV local.

Una segunda alternativa sería cifrar esos campos usando la misma función `cifrar()` de `src/seguridad.py`. Sin embargo, para este caso la opción más simple y segura es no guardarlos, porque no son necesarios para entender por qué una fila fue rechazada.

## Propuesta de roles

Como mejora futura, el sistema podría trabajar con roles básicos de acceso.

| Rol           | Puede hacer                                                                       | No debería poder hacer                                 |
| ------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Administrador | Ejecutar el pipeline, hacer reset, ver datos, revisar logs y configurar variables | Sin restricción principal                              |
| Operador      | Ejecutar el pipeline, ver logs y revisar KPIs                                     | Hacer reset o modificar variables                      |
| Lector        | Ver el panel, los conteos y los KPIs                                              | Ejecutar procesos, hacer reset o cambiar configuración |

En Supabase esto podría reflejarse con permisos separados. Por ejemplo, un rol de solo lectura para consultas, un rol de escritura limitada para el pipeline y un rol administrador para tareas completas. Esta propuesta todavía no está implementada, pero sirve como diseño de seguridad para una versión productiva.

## Protección de `/api/run` y `/api/reset`

La mejora más directa sería exigir un token para usar los endpoints críticos.

Una forma simple de hacerlo, sin agregar librerías nuevas, sería crear una variable de entorno llamada `PANEL_TOKEN`. Luego, el servidor compararía ese token con una cabecera enviada por el panel. Si el token no existe o no coincide, el servidor debería responder con código `401 Unauthorized`.

Además, el endpoint `/api/reset` debería quedar deshabilitado en producción o disponible solo en entorno local. Esto reduce el riesgo de que alguien borre tablas accidentalmente o de forma externa.

## Variables configuradas en Render

En Render solo se deben declarar los nombres de las variables necesarias, no sus valores. Las principales son:

* `FERNET_KEY`
* `DATABASE_URL`

Ambas deben mantenerse como variables de entorno privadas. En el repositorio no deben aparecer valores reales.

## Conclusión de seguridad

El pipeline ya tiene controles importantes: cifra identificadores en la tabla principal, evita subir secretos al repositorio, usa variables de entorno en Render, enmascara datos en logs y valida las etapas permitidas antes de ejecutar procesos.

Sin embargo, todavía existen dos riesgos relevantes. El primero es que `/api/run` y `/api/reset` no tienen autenticación. El segundo es que la tabla `rechazados` guarda identificadores en texto claro.

Por eso, las mejoras prioritarias son:

1. agregar autenticación por token a los endpoints críticos;
2. deshabilitar `/api/reset` en producción;
3. minimizar los datos guardados en la tabla `rechazados`;
4. revisar permisos de Supabase y aplicar el principio de mínimo privilegio.

Con estas mejoras, el proyecto quedaría mucho más preparado para un escenario real, aunque actualmente trabaje con datos sintéticos.

