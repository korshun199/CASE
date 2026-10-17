"""Декодирование выходов YOLOv8 для приложения VIDEOSCAN."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Detection:
    """Один объект после фильтрации и подавления дубликатов."""

    class_id: int
    class_name: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


def decode_yolov8(
    output: np.ndarray,
    class_names: list[str],
    confidence_threshold: float,
    nms_threshold: float,
) -> list[Detection]:
    """Преобразует выход YOLOv8 формата (1, 4+классы, кандидаты) в объекты."""
    if output.ndim != 3 or output.shape[0] != 1 or output.shape[1] != 4 + len(class_names):
        raise ValueError("Выход YOLOv8 не совпадает с количеством настроенных классов")

    boxes: list[list[int]] = []
    scores: list[float] = []
    identifiers: list[int] = []
    for row in output[0].T:
        class_id = int(np.argmax(row[4:]))
        confidence = float(row[4 + class_id])
        if confidence < confidence_threshold:
            continue
        center_x, center_y, width, height = row[:4]
        boxes.append([int(center_x - width / 2), int(center_y - height / 2), int(width), int(height)])
        scores.append(confidence)
        identifiers.append(class_id)

    selected = cv2.dnn.NMSBoxes(boxes, scores, confidence_threshold, nms_threshold)
    return [
        Detection(identifiers[int(index)], class_names[identifiers[int(index)]], scores[int(index)], *boxes[int(index)])
        for index in selected
    ]
