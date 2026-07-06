from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    question: str = Field(..., description="Operator question regarding Textile SOP", example="What is the safe temperature for synthetic fabric?")

class QueryResponse(BaseModel):
    question: str
    retrieved_sop: str
    vector_distance: float
    ai_answer: str
