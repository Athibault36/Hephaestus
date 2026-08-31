# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
CPG (Code Property Graph) Memory Integration
Neo4j/Kuzu for code graphs + LanceDB for visual/asset memory
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple, Union

import lancedb
import numpy as np
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from pydantic import BaseModel, Field


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class CodeNode:
    """Base class for CPG nodes."""
    id: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    labels: List[str] = field(default_factory=list)


@dataclass
class CodeEdge:
    """CPG edge between nodes."""
    source: str
    target: str
    edge_type: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileNode(CodeNode):
    path: str
    language: str
    size: int
    hash: str


@dataclass
class ClassNode(CodeNode):
    name: str
    file_path: str
    line_start: int
    line_end: int
    methods: List[str] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)
    inherits: List[str] = field(default_factory=list)


@dataclass
class FunctionNode(CodeNode):
    name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str
    docstring: str = ""
    params: List[Dict[str, str]] = field(default_factory=list)
    return_type: str = ""
    is_async: bool = False
    is_method: bool = False
    class_name: Optional[str] = None


@dataclass
class ImportNode(CodeNode):
    module: str
    imported_names: List[str]
    file_path: str
    line: int


@dataclass
class CallEdge(CodeEdge):
    caller: str
    callee: str
    line: int


@dataclass
class VisualMemoryEntry:
    """Visual memory entry for viewport history."""
    id: str
    timestamp: float
    frame_id: int
    clip_embedding: np.ndarray  # 512-dim CLIP embedding
    thumbnail_path: str
    viewport_metadata: Dict[str, Any]
    detected_objects: List[Dict[str, Any]]
    agent_context: str  # What the agent was doing
    tags: List[str] = field(default_factory=list)


# ─── Abstract Stores ──────────────────────────────────────────────────────────

class GraphStore(ABC):
    """Abstract graph store for CPG."""
    
    @abstractmethod
    async def connect(self) -> bool:
        pass
    
    @abstractmethod
    async def close(self):
        pass
    
    @abstractmethod
    async def upsert_nodes(self, nodes: List[CodeNode]):
        pass
    
    @abstractmethod
    async def upsert_edges(self, edges: List[CodeEdge]):
        pass
    
    @abstractmethod
    async def query_neighbors(
        self, 
        node_id: str, 
        edge_types: List[str] = None,
        max_depth: int = 1,
        limit: int = 100
    ) -> List[CodeNode]:
        pass
    
    @abstractmethod
    async def query_subgraph(
        self,
        node_ids: List[str],
        max_depth: int = 2
    ) -> Tuple[List[CodeNode], List[CodeEdge]]:
        pass
    
    @abstractmethod
    async def find_nodes_by_property(
        self,
        label: str,
        property_name: str,
        property_value: Any
    ) -> List[CodeNode]:
        pass
    
    @abstractmethod
    async def get_call_graph(
        self,
        function_id: str,
        direction: str = "both",  # "callers", "callees", "both"
        max_depth: int = 3
    ) -> Tuple[List[CodeNode], List[CallEdge]]:
        pass
    
    @abstractmethod
    async def get_impact_analysis(
        self,
        node_id: str,
        max_depth: int = 3
    ) -> List[CodeNode]:
        pass


class VectorStore(ABC):
    """Abstract vector store for embeddings."""
    
    @abstractmethod
    async def connect(self) -> bool:
        pass
    
    @abstractmethod
    async def close(self):
        pass
    
    @abstractmethod
    async def upsert_vectors(
        self,
        table_name: str,
        vectors: List[np.ndarray],
        metadata: List[Dict[str, Any]],
        ids: List[str]
    ):
        pass
    
    @abstractmethod
    async def search(
        self,
        table_name: str,
        query_vector: np.ndarray,
        limit: int = 10,
        filter_expr: str = None
    ) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def hybrid_search(
        self,
        table_name: str,
        query_vector: np.ndarray,
        query_text: str,
        limit: int = 10,
        alpha: float = 0.5
    ) -> List[Dict[str, Any]]:
        pass


# ─── Neo4j Implementation ─────────────────────────────────────────────────────

class Neo4jGraphStore(GraphStore):
    """Neo4j-backed CPG store."""
    
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver: Optional[AsyncDriver] = None
    
    async def connect(self) -> bool:
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                database=self.database,
            )
            # Verify connection
            async with self.driver.session() as session:
                await session.run("RETURN 1")
            
            # Create indexes
            await self._create_indexes()
            return True
        except Exception as e:
            print(f"Neo4j connection failed: {e}")
            return False
    
    async def _create_indexes(self):
        indexes = [
            "CREATE INDEX file_path_idx IF NOT EXISTS FOR (f:File) ON (f.path)",
            "CREATE INDEX class_name_idx IF NOT EXISTS FOR (c:Class) ON (c.name)",
            "CREATE INDEX function_name_idx IF NOT EXISTS FOR (f:Function) ON (f.name)",
            "CREATE INDEX function_file_idx IF NOT EXISTS FOR (f:Function) ON (f.file_path)",
            "CREATE INDEX import_module_idx IF NOT EXISTS FOR (i:Import) ON (i.module)",
        ]
        async with self.driver.session() as session:
            for idx in indexes:
                try:
                    await session.run(idx)
                except Exception:
                    pass  # Index may already exist
    
    async def close(self):
        if self.driver:
            await self.driver.close()
    
    async def upsert_nodes(self, nodes: List[CodeNode]):
        if not nodes:
            return
        
        async with self.driver.session() as session:
            for node in nodes:
                labels = ":".join(node.labels) if node.labels else node.node_type
                props = {**node.properties, "id": node.id, "updated_at": datetime.utcnow().isoformat()}
                
                # Build SET clause
                set_clause = ", ".join([f"n.{k} = ${k}" for k in props.keys()])
                
                query = f"""
                MERGE (n:{labels} {{id: $id}})
                SET {set_clause}
                """
                await session.run(query, **props)
    
    async def upsert_edges(self, edges: List[CodeEdge]):
        if not edges:
            return
        
        async with self.driver.session() as session:
            for edge in edges:
                query = f"""
                MATCH (source {{id: $source}}), (target {{id: $target}})
                MERGE (source)-[r:{edge.edge_type}]->(target)
                SET r += $props
                """
                props = {**edge.properties, "updated_at": datetime.utcnow().isoformat()}
                await session.run(query, source=edge.source, target=edge.target, props=props)
    
    async def query_neighbors(
        self,
        node_id: str,
        edge_types: List[str] = None,
        max_depth: int = 1,
        limit: int = 100
    ) -> List[CodeNode]:
        edge_filter = ""
        if edge_types:
            edge_filter = f"WHERE type(r) IN {edge_types}"
        
        query = f"""
        MATCH (n {{id: $node_id}})-[r*1..{max_depth}]-(neighbor)
        {edge_filter}
        RETURN DISTINCT neighbor
        LIMIT {limit}
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, node_id=node_id)
            nodes = []
            async for record in result:
                node_data = dict(record["neighbor"])
                nodes.append(CodeNode(
                    id=node_data.pop("id"),
                    node_type=list(record["neighbor"].labels)[0] if record["neighbor"].labels else "Unknown",
                    properties=node_data,
                    labels=list(record["neighbor"].labels)
                ))
            return nodes
    
    async def query_subgraph(
        self,
        node_ids: List[str],
        max_depth: int = 2
    ) -> Tuple[List[CodeNode], List[CodeEdge]]:
        query = f"""
        MATCH (n) WHERE n.id IN $node_ids
        CALL apoc.path.subgraphAll(n, {{maxLevel: {max_depth}}})
        YIELD nodes, relationships
        RETURN nodes, relationships
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, node_ids=node_ids)
            nodes, edges = [], []
            async for record in result:
                for node in record["nodes"]:
                    node_data = dict(node)
                    nodes.append(CodeNode(
                        id=node_data.pop("id"),
                        node_type=list(node.labels)[0] if node.labels else "Unknown",
                        properties=node_data,
                        labels=list(node.labels)
                    ))
                for rel in record["relationships"]:
                    rel_data = dict(rel)
                    edges.append(CodeEdge(
                        source=rel.start_node["id"],
                        target=rel.end_node["id"],
                        edge_type=rel.type,
                        properties=rel_data
                    ))
            return nodes, edges
    
    async def find_nodes_by_property(
        self,
        label: str,
        property_name: str,
        property_value: Any
    ) -> List[CodeNode]:
        query = f"""
        MATCH (n:{label}) WHERE n.{property_name} = $value
        RETURN n
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, value=property_value)
            nodes = []
            async for record in result:
                node_data = dict(record["n"])
                nodes.append(CodeNode(
                    id=node_data.pop("id"),
                    node_type=label,
                    properties=node_data,
                    labels=[label]
                ))
            return nodes
    
    async def get_call_graph(
        self,
        function_id: str,
        direction: str = "both",
        max_depth: int = 3
    ) -> Tuple[List[CodeNode], List[CallEdge]]:
        if direction == "callers":
            pattern = "(caller:Function)-[:CALLS*1..{max_depth}]->(callee:Function {{id: $function_id}})"
        elif direction == "callees":
            pattern = "(caller:Function {{id: $function_id}})-[:CALLS*1..{max_depth}]->(callee:Function)"
        else:
            pattern = "(caller:Function)-[:CALLS*1..{max_depth}]-(callee:Function {{id: $function_id}})"
        
        query = f"""
        MATCH {pattern}
        RETURN DISTINCT caller, callee
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, function_id=function_id)
            nodes, edges = [], []
            seen = set()
            
            async for record in result:
                for role in ["caller", "callee"]:
                    node = record[role]
                    node_data = dict(node)
                    nid = node_data.pop("id")
                    if nid not in seen:
                        seen.add(nid)
                        nodes.append(CodeNode(
                            id=nid,
                            node_type="Function",
                            properties=node_data,
                            labels=list(node.labels)
                        ))
                
                # Edge info would need separate query
                # Simplified for now
            
            return nodes, edges
    
    async def get_impact_analysis(
        self,
        node_id: str,
        max_depth: int = 3
    ) -> List[CodeNode]:
        """Find all nodes that would be affected by changing this node."""
        query = f"""
        MATCH (n {{id: $node_id}})<-[:CALLS|INHERITS|USES|IMPORTS*1..{max_depth}]-(affected)
        RETURN DISTINCT affected
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, node_id=node_id)
            nodes = []
            async for record in result:
                node_data = dict(record["affected"])
                nodes.append(CodeNode(
                    id=node_data.pop("id"),
                    node_type=list(record["affected"].labels)[0] if record["affected"].labels else "Unknown",
                    properties=node_data,
                    labels=list(record["affected"].labels)
                ))
            return nodes


# ─── Kuzu Implementation (Embedded, Fast) ─────────────────────────────────────

class KuzuGraphStore(GraphStore):
    """Kuzu embedded graph database for CPG (faster, no server needed)."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
    
    async def connect(self) -> bool:
        try:
            import kuzu
            self.db = kuzu.Database(self.db_path)
            self.conn = kuzu.Connection(self.db)
            
            # Create schema
            await self._create_schema()
            return True
        except Exception as e:
            print(f"Kuzu connection failed: {e}")
            return False
    
    async def _create_schema(self):
        # Node tables
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS File (
                id STRING, path STRING, language STRING, size INT64, hash STRING,
                PRIMARY KEY (id)
            )
        """)
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Class (
                id STRING, name STRING, file_path STRING, line_start INT64, line_end INT64,
                methods STRING, attributes STRING, inherits STRING,
                PRIMARY KEY (id)
            )
        """)
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Function (
                id STRING, name STRING, file_path STRING, line_start INT64, line_end INT64,
                signature STRING, docstring STRING, params STRING, return_type STRING,
                is_async BOOLEAN, is_method BOOLEAN, class_name STRING,
                PRIMARY KEY (id)
            )
        """)
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Import (
                id STRING, module STRING, imported_names STRING, file_path STRING, line INT64,
                PRIMARY KEY (id)
            )
        """)
        
        # Relationship tables
        self.conn.execute("CREATE REL TABLE IF NOT EXISTS CONTAINS (FROM File TO Class)")
        self.conn.execute("CREATE REL TABLE IF NOT EXISTS CONTAINS_FUNC (FROM File TO Function)")
        self.conn.execute("CREATE REL TABLE IF NOT EXISTS CONTAINS_IMPORT (FROM File TO Import)")
        self.conn.execute("CREATE REL TABLE IF NOT EXISTS CALLS (FROM Function TO Function, line INT64)")
        self.conn.execute("CREATE REL TABLE IF NOT EXISTS INHERITS (FROM Class TO Class)")
        self.conn.execute("CREATE REL TABLE IF NOT EXISTS IMPORTS (FROM Function TO Import)")
        self.conn.execute("CREATE REL TABLE IF NOT EXISTS DEFINES (FROM Class TO Function)")
    
    async def close(self):
        pass  # Kuzu closes automatically
    
    async def upsert_nodes(self, nodes: List[CodeNode]):
        for node in nodes:
            if isinstance(node, FileNode):
                self.conn.execute("""
                    MERGE (f:File {id: $id}) SET f.path = $path, f.language = $language, 
                        f.size = $size, f.hash = $hash
                """, id=node.id, path=node.path, language=node.language, 
                    size=node.size, hash=node.hash)
            elif isinstance(node, ClassNode):
                self.conn.execute("""
                    MERGE (c:Class {id: $id}) SET c.name = $name, c.file_path = $file_path,
                        c.line_start = $line_start, c.line_end = $line_end,
                        c.methods = $methods, c.attributes = $attributes, c.inherits = $inherits
                """, id=node.id, name=node.name, file_path=node.file_path,
                    line_start=node.line_start, line_end=node.line_end,
                    methods=json.dumps(node.methods), attributes=json.dumps(node.attributes),
                    inherits=json.dumps(node.inherits))
            elif isinstance(node, FunctionNode):
                self.conn.execute("""
                    MERGE (fn:Function {id: $id}) SET fn.name = $name, fn.file_path = $file_path,
                        fn.line_start = $line_start, fn.line_end = $line_end,
                        fn.signature = $signature, fn.docstring = $docstring,
                        fn.params = $params, fn.return_type = $return_type,
                        fn.is_async = $is_async, fn.is_method = $is_method, fn.class_name = $class_name
                """, id=node.id, name=node.name, file_path=node.file_path,
                    line_start=node.line_start, line_end=node.line_end,
                    signature=node.signature, docstring=node.docstring,
                    params=json.dumps(node.params), return_type=node.return_type,
                    is_async=node.is_async, is_method=node.is_method, class_name=node.class_name or "")
            elif isinstance(node, ImportNode):
                self.conn.execute("""
                    MERGE (i:Import {id: $id}) SET i.module = $module, i.imported_names = $imported_names,
                        i.file_path = $file_path, i.line = $line
                """, id=node.id, module=node.module, 
                    imported_names=json.dumps(node.imported_names),
                    file_path=node.file_path, line=node.line)
    
    async def upsert_edges(self, edges: List[CodeEdge]):
        for edge in edges:
            if edge.edge_type == "CALLS":
                self.conn.execute("""
                    MATCH (caller:Function {id: $source}), (callee:Function {id: $target})
                    MERGE (caller)-[:CALLS {line: $line}]->(callee)
                """, source=edge.source, target=edge.target, line=edge.properties.get("line", 0))
            elif edge.edge_type == "INHERITS":
                self.conn.execute("""
                    MATCH (child:Class {id: $source}), (parent:Class {id: $target})
                    MERGE (child)-[:INHERITS]->(parent)
                """, source=edge.source, target=edge.target)
            # ... other edge types
    
    async def query_neighbors(
        self,
        node_id: str,
        edge_types: List[str] = None,
        max_depth: int = 1,
        limit: int = 100
    ) -> List[CodeNode]:
        # Kuzu doesn't have native variable-length paths yet
        # Use multiple queries for each depth
        return []
    
    async def query_subgraph(
        self,
        node_ids: List[str],
        max_depth: int = 2
    ) -> Tuple[List[CodeNode], List[CodeEdge]]:
        return [], []
    
    async def find_nodes_by_property(
        self,
        label: str,
        property_name: str,
        property_value: Any
    ) -> List[CodeNode]:
        query = f"MATCH (n:{label}) WHERE n.{property_name} = $value RETURN n"
        result = self.conn.execute(query, value=property_value)
        # Parse result
        return []
    
    async def get_call_graph(
        self,
        function_id: str,
        direction: str = "both",
        max_depth: int = 3
    ) -> Tuple[List[CodeNode], List[CallEdge]]:
        return [], []
    
    async def get_impact_analysis(
        self,
        node_id: str,
        max_depth: int = 3
    ) -> List[CodeNode]:
        return []


# ─── LanceDB Vector Store ─────────────────────────────────────────────────────

class LanceDBVectorStore(VectorStore):
    """LanceDB for multimodal embeddings (code, docs, visual)."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = None
        self.tables: Dict[str, Any] = {}
    
    async def connect(self) -> bool:
        try:
            self.db = lancedb.connect(self.db_path)
            await self._create_tables()
            return True
        except Exception as e:
            print(f"LanceDB connection failed: {e}")
            return False
    
    async def _create_tables(self):
        # Code embeddings table
        if "code_chunks" not in self.db.table_names():
            self.tables["code_chunks"] = self.db.create_table(
                "code_chunks",
                data=[{
                    "vector": np.zeros(768, dtype=np.float32),
                    "id": "",
                    "file_path": "",
                    "chunk_type": "",
                    "content": "",
                    "symbols": "",
                    "git_hash": "",
                    "language": "",
                    "timestamp": 0.0,
                }],
                mode="overwrite"
            )
        
        # Visual memory table
        if "visual_memory" not in self.db.table_names():
            self.tables["visual_memory"] = self.db.create_table(
                "visual_memory",
                data=[{
                    "vector": np.zeros(512, dtype=np.float32),
                    "id": "",
                    "timestamp": 0.0,
                    "frame_id": 0,
                    "thumbnail_path": "",
                    "viewport_metadata": "",
                    "detected_objects": "",
                    "agent_context": "",
                    "tags": "",
                }],
                mode="overwrite"
            )
        
        # Documentation/decision table
        if "project_memory" not in self.db.table_names():
            self.tables["project_memory"] = self.db.create_table(
                "project_memory",
                data=[{
                    "vector": np.zeros(768, dtype=np.float32),
                    "id": "",
                    "type": "",
                    "title": "",
                    "content": "",
                    "tags": "",
                    "timestamp": 0.0,
                    "source": "",
                }],
                mode="overwrite"
            )
    
    async def close(self):
        pass
    
    async def upsert_vectors(
        self,
        table_name: str,
        vectors: List[np.ndarray],
        metadata: List[Dict[str, Any]],
        ids: List[str]
    ):
        table = self.db.open_table(table_name)
        data = []
        for vec, meta, id_ in zip(vectors, metadata, ids):
            record = {"vector": vec.astype(np.float32), "id": id_}
            record.update(meta)
            data.append(record)
        table.add(data)
    
    async def search(
        self,
        table_name: str,
        query_vector: np.ndarray,
        limit: int = 10,
        filter_expr: str = None
    ) -> List[Dict[str, Any]]:
        table = self.db.open_table(table_name)
        query = table.search(query_vector.astype(np.float32)).limit(limit)
        if filter_expr:
            query = query.where(filter_expr)
        return query.to_list()
    
    async def hybrid_search(
        self,
        table_name: str,
        query_vector: np.ndarray,
        query_text: str,
        limit: int = 10,
        alpha: float = 0.5
    ) -> List[Dict[str, Any]]:
        # LanceDB supports hybrid search via FTS + vector
        table = self.db.open_table(table_name)
        # This would use LanceDB's hybrid search when available
        return await self.search(table_name, query_vector, limit)


# ─── Memory Manager (High-Level API) ──────────────────────────────────────────

@dataclass
class MemoryConfig:
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"
    use_kuzu: bool = False
    kuzu_path: str = "ProjectMemory/cpg.kuzu"
    lancedb_path: str = "ProjectMemory/lancedb"
    clip_model: str = "ViT-L/14"


class MemoryManager:
    """Unified memory manager for CPG + Vector + Visual memory."""
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.graph_store: Optional[GraphStore] = None
        self.vector_store: Optional[VectorStore] = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        # Initialize graph store
        if self.config.use_kuzu:
            self.graph_store = KuzuGraphStore(self.config.kuzu_path)
        else:
            self.graph_store = Neo4jGraphStore(
                self.config.neo4j_uri,
                self.config.neo4j_user,
                self.config.neo4j_password,
                self.config.neo4j_database
            )
        
        graph_ok = await self.graph_store.connect()
        
        # Initialize vector store
        self.vector_store = LanceDBVectorStore(self.config.lancedb_path)
        vector_ok = await self.vector_store.connect()
        
        self._initialized = graph_ok and vector_ok
        return self._initialized
    
    async def close(self):
        if self.graph_store:
            await self.graph_store.close()
        if self.vector_store:
            await self.vector_store.close()
    
    # ─── CPG Operations ───────────────────────────────────────────────────────
    
    async def ingest_codebase(self, repo_path: str) -> Dict[str, int]:
        """Parse codebase and populate CPG."""
        from tree_sitter import Language, Parser
        # This would use tree-sitter to parse all files
        # For each file, extract: classes, functions, imports, calls
        # Upsert to graph store
        return {"files": 0, "classes": 0, "functions": 0, "imports": 0, "calls": 0}
    
    async def get_context_for_task(
        self,
        task_description: str,
        file_paths: List[str] = None,
        max_tokens: int = 8000
    ) -> Dict[str, Any]:
        """Retrieve relevant context for a task (RAG + Graph)."""
        context = {
            "code_chunks": [],
            "call_graph": {},
            "related_files": [],
            "decisions": [],
        }
        
        # 1. Vector search for relevant code chunks
        if self.vector_store:
            # Would embed task_description and search
            pass
        
        # 2. Graph traversal for call graphs
        if file_paths and self.graph_store:
            for path in file_paths:
                # Find functions in file, get call graph
                pass
        
        # 3. Search project memory for decisions
        if self.vector_store:
            pass
        
        return context
    
    async def record_decision(
        self,
        decision_type: str,
        title: str,
        content: str,
        tags: List[str],
        source: str,
        embedding: np.ndarray = None
    ):
        """Record a design decision to project memory."""
        if self.vector_store:
            await self.vector_store.upsert_vectors(
                "project_memory",
                [embedding] if embedding is not None else [np.zeros(768)],
                [{
                    "type": decision_type,
                    "title": title,
                    "content": content,
                    "tags": json.dumps(tags),
                    "timestamp": datetime.utcnow().timestamp(),
                    "source": source,
                }],
                [str(uuid.uuid4())]
            )
    
    # ─── Visual Memory Operations ─────────────────────────────────────────────
    
    async def add_visual_memory(
        self,
        frame_id: int,
        clip_embedding: np.ndarray,
        thumbnail_path: str,
        viewport_metadata: Dict[str, Any],
        detected_objects: List[Dict[str, Any]],
        agent_context: str,
        tags: List[str] = None
    ):
        """Store visual memory from viewport capture."""
        if self.vector_store:
            await self.vector_store.upsert_vectors(
                "visual_memory",
                [clip_embedding],
                [{
                    "timestamp": datetime.utcnow().timestamp(),
                    "frame_id": frame_id,
                    "thumbnail_path": thumbnail_path,
                    "viewport_metadata": json.dumps(viewport_metadata),
                    "detected_objects": json.dumps(detected_objects),
                    "agent_context": agent_context,
                    "tags": json.dumps(tags or []),
                }],
                [f"frame_{frame_id}_{uuid.uuid4().hex[:8]}"]
            )
    
    async def search_visual_memory(
        self,
        query_embedding: np.ndarray,
        limit: int = 10,
        time_range: Tuple[float, float] = None
    ) -> List[Dict[str, Any]]:
        """Search visual memory by CLIP embedding."""
        if self.vector_store:
            filter_expr = None
            if time_range:
                filter_expr = f"timestamp >= {time_range[0]} AND timestamp <= {time_range[1]}"
            return await self.vector_store.search(
                "visual_memory",
                query_embedding,
                limit=limit,
                filter_expr=filter_expr
            )
        return []
    
    async def get_visual_timeline(
        self,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent visual memory timeline."""
        if self.vector_store:
            table = self.vector_store.db.open_table("visual_memory")
            return table.to_pandas().sort_values("timestamp", ascending=False).head(limit).to_dict("records")
        return []


# ─── Factory ──────────────────────────────────────────────────────────────────

async def create_memory_manager(config: MemoryConfig = None) -> MemoryManager:
    """Create and initialize memory manager."""
    config = config or MemoryConfig()
    manager = MemoryManager(config)
    await manager.initialize()
    return manager