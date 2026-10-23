export interface ToolRun {id:number;message_id:number;tool_call_id:string;tool_name:string;status:string;duration_ms:number|null;input_summary:string|null;output_summary:string|null;error_code:number|null;created_at:string;completed_at:string|null}
export interface Evidence {citation_id:string;source_type:'ERP'|'KNOWLEDGE';resource_type:string;resource_id:string|null;knowledge_base_id:number|null;document_id:number|null;chunk_id:number|null;title:string;excerpt:string|null;source_version:number|null;metadata:Record<string,unknown>;observed_at:string;access_status:'ACTIVE'|'STALE'|'FORBIDDEN'|'MISSING'|'UNAVAILABLE'}
export interface Message {id:number;role:string;content:string;status:string;request_id:string;created_at:string;updated_at:string;tool_runs:ToolRun[];evidences:Evidence[];analysis_status?:string}
export interface Conversation {id:number;title:string;status:string;created_at:string;updated_at:string}
export interface ConversationDetail extends Conversation {messages:Message[]}
export interface ConversationList {items:Conversation[];total:number;page:number;page_size:number}
export interface StreamEvent {event:string;data:Record<string,unknown>}
export type ActionType = 'PURCHASE_ORDER_CREATE'|'SALES_ORDER_CREATE'|'INVENTORY_TRANSFER_CREATE';
export interface ProposalValidation {status:'VALID'|'INVALID'|'UNAVAILABLE';revision:number;errors:Array<{code:string;message:string;field?:string}>;warnings:Array<{code:string;message:string;field?:string}>;missing_fields:string[];preview_data:Record<string,unknown>;resource_versions:Record<string,unknown>;validated_at:string;expires_at:string}
export interface ActionProposal {id:number;conversation_id:number;source_message_id:number|null;action_type:ActionType;schema_version:number;status:'DRAFT'|'NEEDS_INPUT'|'READY'|'STALE'|'CANCELLED'|'EXPIRED';current_revision:number;payload:Record<string,unknown>;editable_fields:string[];validation:ProposalValidation|null;expires_at:string;created_at:string;updated_at:string}
export interface ActionProposalList {items:ActionProposal[];total:number;page:number;page_size:number}
export interface ProposalRevision {revision:number;payload:Record<string,unknown>;editor_user_id:number;created_at:string}
export interface CurrentIdentity {user_id:number;tenant_id:number;member_id:number;is_owner:boolean;roles:string[];permissions:string[];authz_version:number}
