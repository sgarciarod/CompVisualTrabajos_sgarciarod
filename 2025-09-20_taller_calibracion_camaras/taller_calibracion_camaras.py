import cv2
import numpy as np
import glob
import os

def seleccionar_archivos():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="Selecciona las imágenes del tablero de ajedrez",
        filetypes=[("Archivos JPG", "*.jpg"), ("Archivos PNG", "*.png"), ("Todos", "*.*")]
    )
    return list(root.tk.splitlist(file_paths))

def calcular_error_reproyeccion(objpoints, imgpoints, rvecs, tvecs, mtx, dist):
    total_error = 0
    for i in range(len(objpoints)):
        imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
        error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2)/len(imgpoints2)
        total_error += error
    return total_error / len(objpoints)

def calibrar_camara_interactivo():
    print("=== Calibración de cámara con tablero de ajedrez ===")
    print("Selecciona las imágenes del tablero (mínimo 15, distintos ángulos y posiciones)...")
    image_files = seleccionar_archivos()
    if len(image_files) < 10:
        print("¡Advertencia! Se recomienda al menos 15 imágenes para buena calibración.")

    chessboard_size = (9, 6)  # Modifica aquí si tu tablero tiene otra configuración
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    objp = np.zeros((np.prod(chessboard_size), 3), np.float32)
    objp[:, :2] = np.mgrid[0:chessboard_size[0], 0:chessboard_size[1]].T.reshape(-1, 2)

    objpoints = []
    imgpoints = []
    img_shape = None

    for fname in image_files:
        img = cv2.imread(fname)
        if img is None:
            print(f"Error cargando {fname}")
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_shape = gray.shape[::-1]
        ret, corners = cv2.findChessboardCorners(gray, chessboard_size, None)
        if ret:
            objpoints.append(objp)
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            imgpoints.append(corners2)
            cv2.drawChessboardCorners(img, chessboard_size, corners2, ret)
            cv2.imshow('Esquinas detectadas', img)
            cv2.waitKey(500)
        else:
            print(f"Tablero NO detectado en {fname}")
    cv2.destroyAllWindows()

    if len(objpoints) == 0 or len(imgpoints) == 0:
        print("No se detectaron suficientes esquinas. Revisa las imágenes y la configuración del tablero.")
        return

    # Calibración
    print("Calculando calibración...")
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img_shape, None, None)
    print("Matriz de la cámara:\n", mtx)
    print("Coeficientes de distorsión:\n", dist.ravel())

    error_reproy = calcular_error_reproyeccion(objpoints, imgpoints, rvecs, tvecs, mtx, dist)
    print(f"Error medio de reproyección: {error_reproy:.4f} px")

    # Corrección de una imagen de prueba
    img = cv2.imread(image_files[0])
    h, w = img.shape[:2]
    newcameramtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
    dst = cv2.undistort(img, mtx, dist, None, newcameramtx)

    resultado_path = "calibrated_result.jpg"
    cv2.imwrite(resultado_path, dst)
    print(f"Imagen corregida guardada en {resultado_path}")

    # Actividad extra: Corrección en tiempo real (opcional)
    opcion = input("¿Quieres aplicar corrección a la cámara en tiempo real? (s/n): ").strip().lower()
    if opcion == "s":
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            undistorted = cv2.undistort(frame, mtx, dist, None, newcameramtx)
            cv2.imshow('Original', frame)
            cv2.imshow('Corregida', undistorted)
            if cv2.waitKey(1) & 0xFF == 27:  # ESC para salir
                break
        cap.release()
        cv2.destroyAllWindows()
    print("¡Calibración finalizada!")

if __name__ == "__main__":
    calibrar_camara_interactivo()