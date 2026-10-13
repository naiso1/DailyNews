"""Prepare a stopped Power Automate flow using existing Outlook/OneDrive connections.

Apply via notifications/flow-session.ps1, never implicit sign-in cmdlets.
"""
import argparse, copy, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from weekly_report import JST, TEST_TO, week_start

def build(source, now, sample=False):
    kind='sample' if sample else 'weekly'
    connections={k:copy.deepcopy(v) for k,v in source['properties']['connectionReferences'].items() if k in ('shared_office365','shared_onedriveforbusiness')}
    if len(connections)!=2: raise ValueError('Existing Outlook and OneDrive connections are required.')
    def api(conn, operation, parameters, after=None):
        return {'type':'OpenApiConnection','runAfter':{after:['Succeeded']} if after else {},'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/'+conn,'connectionName':conn,'operationId':operation},'parameters':parameters,'authentication':"@parameters('$authentication')",'retryPolicy':{'type':'none'}}}
    def drive(operation,parameters,after=None):return api('shared_onedriveforbusiness',operation,parameters,after)
    directory='/DailyNewsAutomation/weekly-report/'
    packet={'type':'Compose','inputs':"@json(string(body('Get_packet')))",'runAfter':{'Get_packet':['Succeeded']}}
    ledger={'type':'Compose','inputs':"@json(string(body('Get_ledger')))",'runAfter':{'Get_ledger':['Succeeded']}}
    date_expr="formatDateTime(convertTimeZone(utcNow(),'UTC','Tokyo Standard Time'),'yyyy-MM-dd')"
    week_expr="formatDateTime(addDays(convertTimeZone(utcNow(),'UTC','Tokyo Standard Time'),-7),'yyyy-MM-dd')"
    expected_week=(week_start(now.date())-timedelta(days=7)).isoformat()
    conditions=[{'equals':["@outputs('Packet')?['schema']",1]},
        {'equals':["@outputs('Packet')?['to']",TEST_TO]},
        {'not':{'equals':["@outputs('Ledger')?['reportKey']","@outputs('Packet')?['reportKey']"]}},
        {'equals':["@outputs('Packet')?['reportKey']",expected_week if sample else '@'+week_expr]},
        {'equals':['@'+date_expr,now.date().isoformat() if sample else "@outputs('Packet')?['dueDate']"]}]
    def ledger_body(state):
        return "@concat('{\"reportKey\":\"',outputs('Packet')?['reportKey'],'\",\"state\":\""+state+"\",\"runId\":\"',workflow()?['run']?['name'],'\",\"updatedAt\":\"',utcNow(),'\"}')"
    actions={
        'Get_ledger_metadata':drive('GetFileMetadataByPath',{'path':directory+kind+'-ledger.json'}),
        'Claim_delivery':drive('UpdateFile',{'id':"@body('Get_ledger_metadata')?['Id']",'body':ledger_body('claimed')},'Get_ledger_metadata'),
        'Send_report':api('shared_office365','SendEmailV2',{'emailMessage/To':TEST_TO,
            'emailMessage/Subject':"@outputs('Packet')?['subject']",'emailMessage/Body':"@outputs('Packet')?['body']",
            'emailMessage/Attachments':[{'Name':"@outputs('Packet')?['attachmentName']",'ContentBytes':"@outputs('Packet')?['attachmentBase64']"}],
            'emailMessage/Importance':'Normal'},'Claim_delivery'),
        'Record_sent':drive('UpdateFile',{'id':"@body('Get_ledger_metadata')?['Id']",'body':ledger_body('sent')},'Send_report'),
    }
    if sample:recurrence={'frequency':'Day','interval':365,'startTime':(now.astimezone(timezone.utc)+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')}
    else:recurrence={'frequency':'Week','interval':1,'timeZone':'Tokyo Standard Time','startTime':(week_start(now.date())+timedelta(days=7)).isoformat()+'T09:00:00','schedule':{'weekDays':['Monday'],'hours':[9],'minutes':[0]}}
    definition={'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.0.0.0',
        'parameters':copy.deepcopy(source['properties']['definition']['parameters']),
        'triggers':{'Weekly_schedule':{'type':'Recurrence','recurrence':recurrence,'runtimeConfiguration':{'concurrency':{'runs':1}}}},
        'actions':{
            'Get_packet':drive('GetFileContentByPath',{'path':directory+kind+'.json','inferContentType':True}),
            'Packet':packet,
            'Get_ledger':drive('GetFileContentByPath',{'path':directory+kind+'-ledger.json','inferContentType':True},'Packet'),
            'Ledger':ledger,
            'Check_ready_and_unsent':{'type':'If','expression':{'and':conditions},'actions':actions,'else':{'actions':{}},'runAfter':{'Ledger':['Succeeded']}},
        },'outputs':{}}
    return {'properties':{'displayName':'IE開発デイリーニュース '+('週次利用レポート サンプル '+now.date().isoformat() if sample else '週次利用レポート（月曜9時・試行）'),
        'state':'Stopped','definition':definition,'connectionReferences':connections,'environment':copy.deepcopy(source['properties']['environment'])}}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sample',action='store_true');args=p.parse_args()
    payload=build(json.loads(args.source.read_text(encoding='utf-8-sig')),datetime.now(JST),args.sample)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'prepared':str(args.output),'state':'Stopped','recipientCount':1,'sample':args.sample},ensure_ascii=False))
