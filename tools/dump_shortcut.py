"""Print a compiled shortcut plist as indented pseudo-code, for reviewing a build.

    python tools/dump_shortcut.py src/UMDL.plist [max line width]
"""
import plistlib, sys, json

def ref(a):
    name = a.get('OutputName') or a.get('VariableName') or a.get('Type')
    agg = a.get('Aggrandizements')
    if agg:
        bits = []
        for g in agg:
            bits.append(g.get('DictionaryKey') or g.get('CoercionItemClass') or g.get('PropertyName') or g.get('Type'))
        name += '.' + '.'.join(str(b) for b in bits)
    return '<' + str(name) + '>'

def s(v):
    if isinstance(v, dict):
        val = v.get('Value')
        t = v.get('WFSerializationType')
        if t == 'WFTextTokenString':
            st = val['string']
            att = val.get('attachmentsByRange', {})
            out, last = '', 0
            for k, a in sorted(att.items(), key=lambda kv: int(kv[0][1:].split(',')[0])):
                pos = int(k[1:].split(',')[0])
                # ranges are UTF-16 offsets
                u = st.encode('utf-16-le')
                out += u[last*2:pos*2].decode('utf-16-le') + ref(a)
                last = pos + 1
            out += st.encode('utf-16-le')[last*2:].decode('utf-16-le')
            return json.dumps(out, ensure_ascii=False)
        if t == 'WFTextTokenAttachment':
            return ref(val)
        if t == 'WFDictionaryFieldValue':
            items = val.get('WFDictionaryFieldValueItems', [])
            return '{' + ', '.join(s(i.get('WFKey')) + ': ' + s(i.get('WFValue')) for i in items) + '}'
        if 'Variable' in v and 'Type' in v:
            return s(v['Variable'])
        return '{' + ', '.join(f'{k}: {s(x)}' for k, x in v.items()) + '}'
    if isinstance(v, list):
        return '[' + ', '.join(s(x) for x in v) + ']'
    return json.dumps(v, default=str, ensure_ascii=False)

p = plistlib.load(open(sys.argv[1], 'rb'))
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 400
print({k: v for k, v in p.items() if k != 'WFWorkflowActions'})
acts = p['WFWorkflowActions']
print(len(acts), 'actions')
ind = 0
for i, a in enumerate(acts):
    idn = a['WFWorkflowActionIdentifier'].replace('is.workflow.actions.', '')
    pr = a.get('WFWorkflowActionParameters', {})
    mode = pr.get('WFControlFlowMode')
    if mode in (1, 2): ind -= 1
    extra = ', '.join(f'{k}={s(v)}' for k, v in pr.items() if k not in ('UUID', 'GroupingIdentifier', 'WFControlFlowMode'))
    print('  ' * ind + f'{i}: {idn} {extra}'[:limit])
    if mode in (0, 1): ind += 1
