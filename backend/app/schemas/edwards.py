from typing import Optional
from pydantic import BaseModel


class EdwardsTeamMember(BaseModel):
    first_name: str
    last_name: str
    suffix: Optional[str] = None
    role: Optional[str] = None
    primary: bool = False


class EdwardsHospital(BaseModel):
    edwards_id: Optional[int] = None
    edwards_cid: Optional[str] = None
    name: str
    secondary_name: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    thv: bool = False
    tmtt: bool = False
    teer: bool = False
    ttvr: bool = False
    accepting_patients: bool = False
    active: bool = True
    team_members: list[EdwardsTeamMember] = []
    updated_at: Optional[str] = None
    edwards_search_url: str = "https://treatheartvalvefailure.com/find-a-tavr-hospital"


class EdwardsListResponse(BaseModel):
    hospitals: list[EdwardsHospital]
    total: int
    edwards_search_url: str = "https://treatheartvalvefailure.com/find-a-tavr-hospital"
