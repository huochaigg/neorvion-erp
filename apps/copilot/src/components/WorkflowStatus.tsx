import { Tag } from 'antd';
const COLORS:Record<string,string>={SUCCEEDED:'green',RUNNING:'blue',QUEUED:'cyan',WAITING_INPUT:'orange',WAITING_CONFIRMATION:'gold',WAITING_APPROVAL:'purple',RECONCILING:'geekblue',PAUSED:'default',FAILED:'red',NEEDS_MANUAL_INTERVENTION:'volcano',CANCELLED:'default'};
export function WorkflowStatus({value}:{value:string}){return <Tag color={COLORS[value]??'default'}>{value}</Tag>}
