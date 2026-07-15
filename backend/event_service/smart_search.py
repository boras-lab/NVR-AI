from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from shared.models.event import Event, EventCategory

class SmartSearchEngine:
    """
    Simulated Vector Search Engine.
    In a real-world scenario, this would translate NLP queries to vector embeddings
    using models like CLIP and query a vector DB (e.g., pgvector, Milvus).
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def parse_nlp_query(self, query: str) -> Dict[str, Any]:
        """
        Mock NLP parsing.
        e.g., "red car yesterday" -> {"color": "red", "category": "Vehicle Detected", "time": "yesterday"}
        """
        filters = {}
        query_lower = query.lower()
        
        if "car" in query_lower or "truck" in query_lower or "vehicle" in query_lower:
            filters["category"] = EventCategory.VEHICLE_DETECTED
        elif "person" in query_lower or "man" in query_lower or "woman" in query_lower:
            filters["category"] = EventCategory.PERSON_DETECTED
        elif "face" in query_lower:
            filters["category"] = EventCategory.FACE_RECOGNIZED
            
        return filters

    async def execute_search(self, query: str) -> List[Event]:
        """
        Executes the search based on the NLP query string.
        """
        filters = await self.parse_nlp_query(query)
        
        # Build SQL Query based on filters
        stmt = select(Event)
        
        if "category" in filters:
            stmt = stmt.filter(Event.category == filters["category"])
            
        # Order by newest
        stmt = stmt.order_by(Event.created_at.desc()).limit(50)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
