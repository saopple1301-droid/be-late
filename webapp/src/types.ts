export interface Me {
  id: number
  display_name: string
}

export interface Group {
  id: number
  name: string
  invite_code: string
}

export interface Member {
  id: number
  display_name: string
}

export type MeetupStatus =
  | 'draft'
  | 'collecting_deposit'
  | 'doubt_phase'
  | 'active'
  | 'settling'
  | 'completed'
  | 'cancelled'

export interface MeetupSummary {
  id: number
  place_name: string
  scheduled_at: string
  status: MeetupStatus
  group_id: number
}

export interface Participant {
  user_id: number
  display_name: string
  deposit_amount: number
  deposit_status: string
  arrived: boolean
  is_late: boolean
  declared_minutes: number | null
  declared_deadline_at: string | null
  penalty_amount: number
  payout_amount: number | null
}

export interface MeetupDetail extends MeetupSummary {
  participants: Participant[]
}

export interface LocationEntry {
  user_id: number
  display_name: string
  latitude: number
  longitude: number
  minutes_ago: number
}

export interface DoubtTarget {
  target_id: number
  display_name: string
  my_prediction: boolean | null
}

export interface SettlementRow {
  user_id: number
  display_name: string
  is_late: boolean
  payout_amount: number
  lost_amount: number
  net: number
}
