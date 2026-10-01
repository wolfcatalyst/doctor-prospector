export interface EdwardsTeamMember {
  first_name: string;
  last_name: string;
  suffix?: string;
  role?: string;
  primary: boolean;
}

export interface EdwardsHospital {
  edwards_id?: number;
  edwards_cid?: string;
  name: string;
  secondary_name?: string;
  address?: string;
  city: string;
  state: string;
  zip_code?: string;
  latitude?: number;
  longitude?: number;
  email?: string;
  phone?: string;
  website?: string;
  thv: boolean;
  tmtt: boolean;
  teer: boolean;
  ttvr: boolean;
  accepting_patients: boolean;
  active: boolean;
  team_members: EdwardsTeamMember[];
  updated_at?: string;
  edwards_search_url: string;
}

export interface EdwardsListResponse {
  hospitals: EdwardsHospital[];
  total: number;
  edwards_search_url: string;
}

export interface EdwardsMatchResponse {
  match: EdwardsHospital | null;
  edwards_search_url: string;
}
