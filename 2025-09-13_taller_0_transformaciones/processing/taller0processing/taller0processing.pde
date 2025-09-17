float t;

void setup() {
  size(500, 500);
  rectMode(CENTER);
}

void draw() {
  background(240);
  t = millis() / 1000.0; // Tiempo en segundos

  pushMatrix();

  // Traslación: movimiento ondulado en X
  float x = width/2 + sin(t) * 100;
  float y = height/2 + cos(t) * 50;
  translate(x, y);

  // Rotación sobre el centro del cuadrado
  rotate(t);

  // Escalado oscilante
  float s = 1 + 0.5 * sin(t * 2);
  scale(s);

  // Dibuja el cuadrado
  fill(80, 180, 240);
  stroke(40, 80, 120);
  strokeWeight(3);
  rect(0, 0, 100, 100);

  popMatrix();

  // Opcional: muestra valores en pantalla
  fill(0);
  noStroke();
  textSize(16);
  text("t: " + nf(t, 1, 2), 10, 20);
  text("scale: " + nf(s, 1, 2), 10, 40);
}
