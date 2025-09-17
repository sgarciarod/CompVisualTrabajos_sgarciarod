using UnityEngine;

public class TransformacionesTaller : MonoBehaviour
{
    // Par�metros configurables si quieres modificar en el Editor
    public float translateInterval = 2.0f; // segundos entre traslaciones
    public float translateAmount = 2.0f;   // distancia de traslaci�n
    private float lastTranslateTime = 0;
    private int direction = 1;

    void Update()
    {
        // Traslaci�n aleatoria por eje X cada ciertos segundos
        if (Time.time - lastTranslateTime > translateInterval)
        {
            direction *= -1; // Cambia la direcci�n cada vez
            transform.Translate(Vector3.right * translateAmount * direction, Space.World);
            lastTranslateTime = Time.time;
        }

        // Rotaci�n constante dependiente de Time.deltaTime
        transform.Rotate(Vector3.up, 90f * Time.deltaTime);

        // Escalado oscilante en funci�n de Mathf.Sin(Time.time)
        float scale = 1.0f + 0.5f * Mathf.Sin(Time.time);
        transform.localScale = new Vector3(scale, scale, scale);
    }
}