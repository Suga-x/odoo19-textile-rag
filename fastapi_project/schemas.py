from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    question: str = Field(..., description="Pertanyaan operator mengenai SOP Tekstil", example="Berapa suhu aman kain sintetis?")

class QueryResponse(BaseModel):
    question: str
    retrieved_sop: str
    vector_distance: float
    ai_answer: str