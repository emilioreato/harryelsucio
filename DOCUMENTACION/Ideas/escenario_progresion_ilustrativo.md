# Escenario ilustrativo de progresión

## Recorrido

Después de terminar un análisis, selecciona **Elegir origen en imagen** y haz clic en un solo foco activo que hayas observado. Introduce temperatura del aire, humedad relativa, dirección del viento «desde» (bearing desde norte y sentido horario), velocidad y avance base en píxeles por paso. Puedes registrar la hora/zona y fuente de esos datos para conservar su procedencia. **Generar progresión** solicita al backend una secuencia de frentes; el visor la anima, permite pausarla y recorrer los pasos.

El origen es manual deliberadamente: el modelo no inicia desde toda la superficie candidata ni afirma que una cicatriz quemada continúe ardiendo.

## Ecuación visible

Para esta animación experimental se calculan:

```text
D = ((T + 20) / 80) · (1 − HR / 100)
F_ambiente = 0,75 + 0,5 · D
A_viento = 0,45 · v / (v + 20)
θ_hacia = (θ_desde + 180°) mod 360°
r(θ, k) = k · avance_base · F_ambiente · [1 + A_viento · cos(θ − θ_viento)]
```

`T` está en °C dentro del rango admitido −20…60; `HR` es humedad relativa del aire (0…100 %); `v` es velocidad en km/h; `k` es el número de paso visual. La dirección meteorológica «desde» se invierte para orientar el lóbulo hacia donde sopla el viento. El origen y el frente se dibujan en la rejilla de píxeles de la imagen.

Los coeficientes se usan para una forma visual sencilla, no vienen calibrados con incendios. `D` no es humedad del combustible; `r` está en píxeles, y los pasos no representan minutos ni horas. El control de avance permite experimentar con el tamaño visual de cada paso.

## Límite científico

Esto es un **escenario matemático exploratorio, no una predicción validada ni una herramienta de respuesta**. No modela combustible y su carga, humedad de combustible, relieve/pendiente, continuidad del combustible, barreras, focos secundarios ni variaciones del viento. La temperatura y humedad se presentan únicamente como un modulador ambiental heurístico y no sustituyen esos datos.

La referencia física del repositorio es Rothermel para fuego de superficie. La guía del USDA Forest Service explica que su aplicación requiere parámetros del combustible, humedad del combustible, viento a la altura media de llama y pendiente, además del modelo de combustible; una superficie candidata en un JPG no aporta por sí sola esos datos.

## Código

- Fórmula y validación: `pyroscope/escenarios.py`.
- Endpoint por análisis: `POST /api/jobs/<id>/fire-progression`.
- Interfaz React: panel `Escenario de progresión` en el lateral y capa canvas sobre el visor.

Fuente oficial: [USDA Forest Service, The Rothermel surface fire spread model and associated developments](https://research.fs.usda.gov/treesearch/55928).
