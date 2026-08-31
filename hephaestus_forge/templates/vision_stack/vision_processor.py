# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Vision Stack Processor - Frame decoding, SAM2/YOLO-World inference, structured JSON output.
Runs as a standalone FastAPI service or library.
"""

import base64
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any

import cv2
import numpy as np
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
import uvicorn


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    confidence: float
    label: str


@dataclass
class DetectedObject:
    label: str
    bbox: List[float]  # [x, y, w, h] normalized 0-1
    world_pos: Optional[List[float]] = None  # [x, y, z] in UE world space
    material_slot: Optional[int] = None
    tri_count: Optional[int] = None
    confidence: float = 1.0
    mask: Optional[List[List[int]]] = None  # RLE encoded mask


@dataclass
class SceneGraph:
    objects: List[DetectedObject]
    relationships: List[Dict[str, Any]]  # Spatial/parent-child relationships


@dataclass
class Anomaly:
    type: str  # "z-fighting", "uv_overlap", "missing_collision", "lightmap_overlap"
    severity: str  # "low", "medium", "high", "critical"
    description: str
    affected_actors: List[str]
    location: Optional[List[float]] = None


@dataclass
class VisionResult:
    frame_id: int
    timestamp: float
    objects: List[DetectedObject]
    scene_graph: SceneGraph
    anomalies: List[Anomaly]
    processing_time_ms: float


class FrameRequest(BaseModel):
    frame_id: int
    timestamp: float
    image_b64: str  # Base64 encoded RGB/RGBA image
    width: int
    height: int
    gbuffer: Optional[Dict[str, str]] = None  # Base64 encoded G-Buffer passes


# ─── Vision Processor ─────────────────────────────────────────────────────────

class VisionProcessor:
    """Main vision processing pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Models (loaded lazily)
        self._yolo_model = None
        self._sam2_model = None
        self._clip_model = None
        self._florence_model = None
        
        # Class names for YOLO-World
        self.yolo_classes = [
            "StaticMeshActor", "SkeletalMeshActor", "BlueprintActor",
            "Light", "Camera", "ParticleSystem", "Foliage",
            "WaterBody", "Landscape", "SplineActor"
        ]
    
    @property
    def yolo_model(self):
        if self._yolo_model is None:
            self._load_yolo_world()
        return self._yolo_model
    
    @property
    def sam2_model(self):
        if self._sam2_model is None:
            self._load_sam2()
        return self._sam2_model
    
    def _load_yolo_world(self):
        """Load YOLO-World model for open-vocabulary detection."""
        model_path = self.config.get("detection_model", "yolo_world_l.pt")
        try:
            # Using ultralytics YOLO
            from ultralytics import YOLO
            self._yolo_model = YOLO(model_path)
            self._yolo_model.set_classes(self.yolo_classes)
            self._yolo_model.to(self.device)
        except Exception as e:
            print(f"Failed to load YOLO-World: {e}")
            self._yolo_model = None
    
    def _load_sam2(self):
        """Load SAM2 for segmentation."""
        try:
            # SAM2 loading would go here
            pass
        except Exception as e:
            print(f"Failed to load SAM2: {e}")
            self._sam2_model = None
    
    def decode_frame(self, request: FrameRequest) -> np.ndarray:
        """Decode base64 frame to numpy array."""
        img_data = base64.b64decode(request.image_b64)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        
        if frame is None:
            raise ValueError("Failed to decode frame")
        
        # Convert BGR to RGB
        if frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        elif frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)
        
        return frame
    
    def decode_gbuffer(self, gbuffer: Dict[str, str]) -> Dict[str, np.ndarray]:
        """Decode G-Buffer passes."""
        decoded = {}
        for name, b64_data in gbuffer.items():
            img_data = base64.b64decode(b64_data)
            nparr = np.frombuffer(img_data, np.uint8)
            decoded[name] = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        return decoded
    
    def detect_objects(self, frame: np.ndarray) -> List[DetectedObject]:
        """Run YOLO-World detection."""
        objects = []
        
        if self.yolo_model is None:
            return objects
        
        results = self.yolo_model(frame, verbose=False)
        
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    
                    # Normalize to 0-1
                    h, w = frame.shape[:2]
                    bbox = [
                        x1 / w, y1 / h,
                        (x2 - x1) / w, (y2 - y1) / h
                    ]
                    
                    label = self.yolo_classes[cls_id] if cls_id < len(self.yolo_classes) else f"class_{cls_id}"
                    
                    objects.append(DetectedObject(
                        label=label,
                        bbox=bbox,
                        confidence=conf
                    ))
        
        return objects
    
    def segment_objects(self, frame: np.ndarray, objects: List[DetectedObject]) -> List[DetectedObject]:
        """Run SAM2 segmentation on detected objects."""
        if self.sam2_model is None:
            return objects
        
        # SAM2 inference would go here
        # For each object, generate mask from bbox
        
        return objects
    
    def estimate_world_positions(
        self,
        objects: List[DetectedObject],
        gbuffer: Dict[str, np.ndarray],
        view_matrix: np.ndarray,
        proj_matrix: np.ndarray
    ) -> List[DetectedObject]:
        """Estimate world positions from depth buffer and bbox centers."""
        depth = gbuffer.get("depth")
        if depth is None:
            return objects
        
        h, w = depth.shape[:2]
        
        for obj in objects:
            # Get bbox center in pixel coordinates
            cx = int((obj.bbox[0] + obj.bbox[2] / 2) * w)
            cy = int((obj.bbox[1] + obj.bbox[3] / 2) * h)
            
            # Clamp
            cx = np.clip(cx, 0, w - 1)
            cy = np.clip(cy, 0, h - 1)
            
            # Read depth
            z = depth[cy, cx]
            if z > 0 and z < 1.0:  # Valid depth
                # Unproject to world space
                # This is simplified - real implementation needs proper unprojection
                x = (cx / w) * 2 - 1
                y = (cy / h) * 2 - 1
                obj.world_pos = [float(x), float(y), float(z)]
        
        return objects
    
    def detect_anomalies(
        self,
        frame: np.ndarray,
        objects: List[DetectedObject],
        gbuffer: Dict[str, np.ndarray]
    ) -> List[Anomaly]:
        """Detect visual anomalies."""
        anomalies = []
        
        # Z-fighting detection (check depth variance in small regions)
        depth = gbuffer.get("depth")
        if depth is not None:
            # Simplified: check for high frequency depth changes
            pass
        
        # UV overlap detection (would need UV buffer)
        # Missing collision (check for actors without collision)
        # Lightmap overlap (check lightmap UVs)
        
        return anomalies
    
    def build_scene_graph(self, objects: List[DetectedObject]) -> SceneGraph:
        """Build scene graph from detected objects."""
        relationships = []
        
        # Spatial relationships (above, below, inside, near)
        for i, obj_a in enumerate(objects):
            for j, obj_b in enumerate(objects):
                if i >= j:
                    continue
                
                # Simple distance-based relationship
                if obj_a.world_pos and obj_b.world_pos:
                    dist = np.linalg.norm(
                        np.array(obj_a.world_pos) - np.array(obj_b.world_pos)
                    )
                    if dist < 2.0:  # 2 meters
                        relationships.append({
                            "type": "near",
                            "subject": obj_a.label,
                            "object": obj_b.label,
                            "distance": float(dist)
                        })
        
        return SceneGraph(objects=objects, relationships=relationships)
    
    def process_frame(self, request: FrameRequest) -> VisionResult:
        """Main processing pipeline."""
        start_time = time.time()
        
        # Decode frame
        frame = self.decode_frame(request)
        
        # Decode G-Buffer if available
        gbuffer = {}
        if request.gbuffer:
            gbuffer = self.decode_gbuffer(request.gbuffer)
        
        # Detect objects
        objects = self.detect_objects(frame)
        
        # Segment objects
        objects = self.segment_objects(frame, objects)
        
        # Estimate world positions
        if gbuffer:
            # Would need view/proj matrices from UE
            view_matrix = np.eye(4)
            proj_matrix = np.eye(4)
            objects = self.estimate_world_positions(
                objects, gbuffer, view_matrix, proj_matrix
            )
        
        # Detect anomalies
        anomalies = self.detect_anomalies(frame, objects, gbuffer)
        
        # Build scene graph
        scene_graph = self.build_scene_graph(objects)
        
        processing_time = (time.time() - start_time) * 1000
        
        return VisionResult(
            frame_id=request.frame_id,
            timestamp=request.timestamp,
            objects=objects,
            scene_graph=scene_graph,
            anomalies=anomalies,
            processing_time_ms=processing_time
        )


# ─── FastAPI Server ───────────────────────────────────────────────────────────

app = FastAPI(title="Hephaestus Vision Stack", version="1.0.0")

# Global processor instance
processor: Optional[VisionProcessor] = None


@app.on_event("startup")
async def startup():
    global processor
    config = {
        "detection_model": "models/yolo_world_l.pt",
        "segmentation_model": "models/sam2_hiera_large.pt",
        "classification_model": "models/open_clip_pytorch_model.bin",
        "captioning_model": "models/florence-2-large.pt",
        "device": "cuda",
        "batch_size": 1,
    }
    processor = VisionProcessor(config)


@app.post("/process", response_model=Dict[str, Any])
async def process_frame(request: FrameRequest):
    """Process a single frame and return structured JSON."""
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    
    result = processor.process_frame(request)
    return asdict(result)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for streaming frame processing."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            request = FrameRequest(**data)
            result = processor.process_frame(request)
            await websocket.send_json(asdict(result))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})


@app.get("/health")
async def health():
    return {"status": "healthy", "device": str(processor.device) if processor else "unknown"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8083)