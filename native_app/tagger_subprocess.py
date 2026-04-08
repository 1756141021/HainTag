"""Standalone tagger inference script — called via subprocess with external Python.

Usage:
    python tagger_subprocess.py <image_path> <model_path> <mapping_path> [gen_threshold] [char_threshold] [categories] [blacklist]

Output: JSON to stdout
"""
import json
import sys
import os

import numpy as np
from PIL import Image


def pad_square(image):
    w, h = image.size
    if w == h:
        return image
    size = max(w, h)
    new_img = Image.new("RGB", (size, size), (255, 255, 255))
    new_img.paste(image, ((size - w) // 2, (size - h) // 2))
    return new_img


def preprocess(image):
    image = image.convert("RGB")
    image = pad_square(image)
    image = image.resize((448, 448), Image.BICUBIC)
    arr = np.array(image, dtype=np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)
    arr = arr[::-1, :, :]
    arr = (arr - 0.5) / 0.5
    return np.expand_dims(arr, 0).copy()


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def main():
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: <image> <model.onnx> <mapping.json> [gen_t] [char_t] [cats] [blacklist]"}))
        sys.exit(1)

    image_path = sys.argv[1]
    model_path = sys.argv[2]
    mapping_path = sys.argv[3]
    gen_threshold = float(sys.argv[4]) if len(sys.argv) > 4 else 0.35
    char_threshold = float(sys.argv[5]) if len(sys.argv) > 5 else 0.70
    categories = set(sys.argv[6].split(",")) if len(sys.argv) > 6 and sys.argv[6] else {"general", "character", "copyright"}
    blacklist = set(sys.argv[7].split(",")) if len(sys.argv) > 7 and sys.argv[7] else set()

    try:
        import onnxruntime as ort
    except ImportError:
        print(json.dumps({"error": "onnxruntime not installed in this Python"}))
        sys.exit(1)

    # Load model
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])

    # Load mapping
    with open(mapping_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    names = []
    cat_map = []
    if isinstance(data, list):
        for entry in data:
            names.append(entry.get("tag", entry.get("name", "")))
            cat_map.append(entry.get("category", "general").lower())
    elif isinstance(data, dict):
        for key, info in data.items():
            names.append(info.get("tag", key) if isinstance(info, dict) else key)
            cat_map.append((info.get("category", "general") if isinstance(info, dict) else "general").lower())

    # Preprocess
    image = Image.open(image_path)
    input_tensor = preprocess(image)

    # Inference
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    outputs = session.run([output_name], {input_name: input_tensor})[0]
    probs = sigmoid(outputs[0])

    # Threshold
    results = {}
    for i, (name, cat, prob) in enumerate(zip(names, cat_map, probs)):
        if cat not in categories:
            continue
        prob = float(prob)
        if cat in ("character", "copyright", "artist"):
            t = char_threshold
        elif cat in ("rating", "quality"):
            t = 0.0
        else:
            t = gen_threshold
        if prob < t:
            continue
        if name in blacklist:
            continue
        if cat not in results:
            results[cat] = []
        results[cat].append([name, prob])

    # Sort and limit rating/quality to top-1
    for cat in results:
        results[cat].sort(key=lambda x: x[1], reverse=True)
        if cat in ("rating", "quality"):
            results[cat] = results[cat][:1]

    print(json.dumps({"results": results}))


if __name__ == "__main__":
    main()
