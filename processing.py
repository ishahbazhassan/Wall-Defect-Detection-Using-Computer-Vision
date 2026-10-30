import cv2
import numpy as np

def detect_defects(input_path, out_path):
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError("Image not found")

    # Convert to grayscale and blur
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Edge detection
    edges = cv2.Canny(blur, 50, 150)

    # Morphological closing to connect broken edges
    kernel = np.ones((3,3), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    defect_count = 0
    for c in contours:
        area = cv2.contourArea(c)
        if area < 150:  # ignore tiny noise
            continue
        defect_count += 1
        x, y, w, h = cv2.boundingRect(c)
        cv2.rectangle(img, (x,y), (x+w,y+h), (0,255,0), 2)

    # Combine original and processed image side by side
    result = np.hstack((cv2.imread(input_path), img))
    cv2.imwrite(out_path, result)

    return defect_count
