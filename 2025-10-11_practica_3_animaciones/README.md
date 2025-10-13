# Animaciones en Three.js: Cinemática Directa, Cinemática Inversa y Principios de Animación

Este práctoca contiene tres ejemplos clave de animación 3D en Three.js: una pierna humana articulada (cinemática directa), una grúa tipo torre (cinemática inversa) y una pelota saltando (principios fundamentales de la animación). Cada proyecto ilustra técnicas y conceptos esenciales para la animación digital.

---

## 1. Animación de Pierna con Cinemática Directa (FK) en Three.js

<div align="center">
<img src="animaciones\Pierna.gif" alt="Animación Pierna FK" width="400">
</div>

### Descripción

Este proyecto muestra la animación de una pierna humana utilizando **cinemática directa (Forward Kinematics, FK)** en Three.js. El modelo 3D se estructura de modo que cada segmento (muslo, pantorrilla, pie) puede rotar respecto a su articulación, simulando el movimiento real de una pierna.

### ¿Cómo se implementó la cinemática directa?

#### Concepto

La cinemática directa consiste en calcular la posición y orientación de cada segmento de una cadena articulada a partir de los ángulos de sus articulaciones, comenzando desde la base (la cadera) y avanzando segmento por segmento.

Para animar una pierna con FK:
- Se define cada segmento: muslo, pantorrilla y pie como partes independientes.
- Cada segmento está vinculado jerárquicamente: el muslo está unido a la cadera, la pantorrilla al muslo (rodilla) y el pie a la pantorrilla (tobillo).
- Al modificar el ángulo de una articulación, todos los segmentos hijos se mueven en consecuencia.

#### Implementación práctica

- Se creó una jerarquía de pivotes (grupos) que representan las articulaciones: cadera, rodilla y tobillo.
- Cada parte del modelo se “engancha” a su pivote correspondiente.
- En cada frame de la animación, se modifican los ángulos de estos pivotes simulando la flexión/extensión de la pierna.
- Así, el movimiento se propaga desde la cadera hacia el pie, logrando un movimiento natural.

#### Ejemplo de animación FK

- Se calcula un ángulo de rotación para la cadera, rodilla y tobillo usando funciones seno/coseno para simular un movimiento cíclico y suave.
- Estos ángulos se aplican en tiempo real a cada pivote, lo que mueve las partes del modelo en cadena.

### Conclusión

La cinemática directa es un método intuitivo y eficiente para animar extremidades y cadenas articuladas, permitiendo control total sobre los ángulos de cada articulación. Es ideal para movimientos donde el control sobre cada articulación es necesario, como caminar, correr o saltar. En Three.js, la implementación es directa gracias a la estructura jerárquica de la escena y la facilidad para manipular transformaciones de grupos y objetos.

---

## 2. Animación de Grúa con Cinemática Inversa (IK) en Three.js

<div align="center">
<img src="animaciones\Grua.gif" alt="Animación Grúa IK" width="400">
</div>

### Descripción

Este proyecto implementa una grúa tipo torre en Three.js que utiliza **cinemática inversa (IK)** para orientar la estructura automáticamente en función de un objetivo visual (target) en el espacio 3D. El usuario puede mover el objetivo con el teclado, y la grúa calcula de forma automática el giro de la base para que la viga apunte hacia ese objetivo y lo siga alrededor de la escena.

### ¿Cómo se implementó la cinemática inversa?

#### Concepto

La cinemática inversa permite calcular cómo deben moverse las articulaciones y partes de un sistema articulado para que su extremo (en este caso, la viga de la grúa) apunte hacia una posición objetivo. A diferencia de la cinemática directa, aquí el usuario define dónde quiere que esté el objetivo y el sistema resuelve los movimientos necesarios.

#### Implementación práctica

- **Rotación de la base:** La grúa gira automáticamente para que la viga apunte y siga al objetivo.
- **Resolución matemática:** Se calcula el ángulo de giro usando trigonometría y el vector entre la base de la grúa y el objetivo.
- **Interacción:** El usuario mueve el objetivo rojo con el teclado y observa cómo la grúa gira en tiempo real para orientarse hacia él.

#### Ejemplo de animación IK

- El usuario mueve el objetivo rojo con el teclado.
- La grúa rota automáticamente para seguir ese punto, mostrando cómo la estructura responde a cambios en la posición del objetivo.

### Conclusión

La cinemática inversa facilita el control de mecanismos articulados, permitiendo animaciones y movimientos automáticos y realistas en 3D. Es especialmente útil en robótica, simulaciones y cualquier sistema donde el usuario quiera controlar la dirección o el punto final del movimiento en vez de cada articulación por separado.

---

## 3. Animación de Pelota Saltando: Anticipación y Squash & Stretch

<div align="center">
<img src="animaciones\Pelota.gif" alt="Animación Pelota Squash & Stretch" width="400">
</div>

### Descripción

Este proyecto muestra una pelota saltando en Three.js, aplicando dos principios fundamentales de la animación tradicional: **Anticipation (anticipación)** y **Squash & Stretch (aplastamiento y estiramiento)**.

### Principios de animación aplicados

#### 1. Anticipation (Anticipación)

Antes de cada salto, la pelota se aplasta y baja ligeramente, simulando que acumula energía para saltar. Este movimiento prepara al espectador para la acción principal y crea expectativa visual.

#### 2. Squash & Stretch (Aplastamiento y Estiramiento)

- **Squash:** Al prepararse para saltar y al impactar contra el suelo, la pelota se aplasta horizontalmente y se reduce en altura.
- **Stretch:** Al subir y descender rápidamente, la pelota se estira verticalmente y se estrecha en los lados, enfatizando velocidad y energía.

#### Ejemplo de animación

La animación es cíclica: la pelota anticipa el salto, se estira en el despegue, sube y cae con variación de forma, y se aplasta al impactar, rebotando con menos energía en cada ciclo.

### Conclusión

La aplicación de los principios de **anticipation** y **squash & stretch** transforma una animación simple en una experiencia visual atractiva y realista, mostrando elasticidad y peso. 


