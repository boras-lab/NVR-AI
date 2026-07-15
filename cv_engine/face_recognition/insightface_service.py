import cv2
import numpy as np
from typing import List, Dict, Optional
import os

# Try importing insightface, fallback gracefully for code generation / structure layout
try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

class FaceRecognitionEngine:
    def __init__(self, use_gpu: bool = True):
        self.face_db = {} # Simulated Face DB: { "embedding_hash": "John Doe" }
        self.app = None
        
        if INSIGHTFACE_AVAILABLE:
            # Initialize FaceAnalysis app
            self.app = FaceAnalysis(name='buffalo_l', providers=['CUDAExecutionProvider' if use_gpu else 'CPUExecutionProvider'])
            self.app.prepare(ctx_id=0 if use_gpu else -1, det_size=(640, 640))
            print("InsightFace initialized.")
        else:
            print("WARNING: insightface package not found. Running in dummy mode.")

    def add_face(self, image: np.ndarray, person_name: str) -> bool:
        """Extracts embedding from an image and adds it to the database."""
        if not self.app: return False
        
        faces = self.app.get(image)
        if len(faces) == 0:
            print("No faces detected to add.")
            return False
            
        # Get the largest face
        largest_face = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]), reverse=True)[0]
        embedding = largest_face.normed_embedding
        
        # In a real app, store to Milvus / pgvector
        self.face_db[person_name] = embedding
        print(f"Added face for {person_name} to database.")
        return True

    def recognize_faces(self, frame: np.ndarray, similarity_threshold: float = 0.5) -> List[Dict]:
        """Detects and recognizes faces in a frame."""
        results = []
        if not self.app: return results
        
        faces = self.app.get(frame)
        for face in faces:
            bbox = face.bbox.astype(int).tolist()
            embedding = face.normed_embedding
            
            best_match = "Unknown"
            highest_sim = -1.0
            
            # Simple dot product for cosine similarity (since embeddings are normed)
            for name, db_emb in self.face_db.items():
                sim = np.dot(embedding, db_emb)
                if sim > highest_sim and sim > similarity_threshold:
                    highest_sim = sim
                    best_match = name
                    
            results.append({
                "bbox": bbox,
                "name": best_match,
                "similarity": float(highest_sim) if highest_sim > 0 else 0.0
            })
            
        return results

if __name__ == "__main__":
    # Test execution
    engine = FaceRecognitionEngine(use_gpu=False)
    # mock_image = np.zeros((480, 640, 3), dtype=np.uint8)
    # engine.add_face(mock_image, "Test Subject")
