"""Validate the saved evidence, do not turn aspirational thresholds into passes."""
import hashlib,json
from support7 import ROOT
from snapshot import inputs

def run():
    r=ROOT/'results'
    assert json.loads((r/'protected-inputs.json').read_text())==inputs()
    real=json.loads((r/'bench-real.json').read_text())
    audit=json.loads((r/'real-audit.json').read_text())
    assert audit['counts']['events']==524934
    assert audit['counts']['wave_alias_mismatch']==audit['counts']['hash_mismatch']==audit['counts']['pair_collision']==0
    assert {x['variant']for x in real['rows']}=={'raw','hash_wave_clean','all_clean'}
    for row in real['rows']:
        assert row['events']==audit['holdout_events']
        for k,total in row['bytes'].items():assert abs(row['B_event'][k]-total/row['events'])<1e-12
    for profile in ('base','rich','alt','drift'):
        b=json.loads((r/f'bench-{profile}.json').read_text());assert len(b['rows'])==6
        for row in b['rows']:
            for k,total in row['bytes'].items():assert abs(row['B_event'][k]-total/row['events'])<1e-12
    native=json.loads((r/'native-csharp.json').read_text())
    native += [json.loads(p.read_text())for p in r.glob('native-real-*.json')]
    assert len(native)==6 and all(x['gc_bytes']==0 and x['python_roundtrip'] for x in native)
    go=json.loads((r/'go-check.json').read_text());assert len(go)==6 and all(x['go_column_parity']for x in go)
    checks={'evidence_integrity':'PASS','protected_files':len(inputs()),'production_rows_audited':audit['counts']['events'],
            'raw_13B_goal':real['rows'][0]['B_event']['v7_dict32']<13,
            'clean_7B_goal':real['rows'][-1]['B_event']['v7_dict32']<7,
            'host_CSharp_typed_column_zeroGC':True,'Unity_IL2CPP_zeroGC':'NOT_MEASURED','phone_5ms':'NOT_MEASURED',
            'battery_temperature':'NOT_MEASURED','production_migration':'NOT_IMPLEMENTED'}
    if (r/'numeric-benchmark.json').exists():
        candidate=json.loads((r/'numeric-benchmark.json').read_text())
        assert len(candidate)==2 and all(row['events']==audit['holdout_events']for row in candidate)
        for row in candidate:
            for key,total in row['bytes'].items():assert abs(row['B_event'][key]-total/row['events'])<1e-12
        native_candidate=json.loads((r/'native-numeric.json').read_text())
        go_candidate=json.loads((r/'go-check-numeric.json').read_text())
        assert len(native_candidate)==len(go_candidate)==6
        assert all(row['gc_bytes']==0 and row['python_roundtrip']for row in native_candidate)
        assert all(row['go_column_parity']for row in go_candidate)
        assert any(set(row.get('numeric_modes_exercised',[]))=={0,1,2,3,4}for row in native_candidate)
        checks['numeric_candidate_raw_13B_goal']=candidate[0]['B_event']['dict32']<13
        checks['numeric_candidate_clean_7B_goal']=candidate[1]['B_event']['dict32']<7
        checks['numeric_candidate_CSharp_zeroGC_Go_parity']='PASS'
    if (r/'tables-benchmark.json').exists():
        tables=json.loads((r/'tables-benchmark.json').read_text())
        assert len(tables)==6 and all(row['events']==audit['holdout_events']for row in tables)
        for row in tables:
            assert row['CSharp_Go_Unity']in ('NOT_PORTED_FOR_NEW_MODELS','SEPARATE_STAGE_EVIDENCE; METADATA_MODEL_NOT_PORTED')
            for key,total in row['bytes'].items():assert abs(row['B_event'][key]-total/row['events'])<1e-12
        costs=json.loads((r/'remaining-column-costs.json').read_text())
        assert costs['baseline_body_bytes']==candidate[1]['bytes']['dict32']
        checks['table_candidate_raw_13B_goal']=min(row['B_event']['dict32']for row in tables if row['variant']=='raw')<13
        checks['table_candidate_clean_7B_goal']=min(row['B_event']['dict32']for row in tables if row['variant']=='all_clean')<7
        checks['table_candidate_Unity_CPU_GC']='NOT_MEASURED_NOT_PORTED'
        if (r/'native-tables.json').exists():
            native_tables=json.loads((r/'native-tables.json').read_text());go_tables=json.loads((r/'go-check-tables.json').read_text())
            assert len(native_tables)==len(go_tables)==4
            assert all(row['gc_bytes']==0 and row['python_roundtrip']and row['python_raw_parity']for row in native_tables)
            assert all(row['go_column_parity']for row in go_tables)
            assert any(set(row.get('string_modes_exercised',[]))=={0,1,2,3,4}for row in native_tables)
            checks['string_candidate_CSharp_zeroGC_Python_raw_Go_parity']='PASS'
            checks['table_candidate_Unity_CPU_GC']='STRING_HOST_ONLY; metadata flag16 NOT_PORTED'
    if (r/'native-frames-corpus.json').exists():
        packets=json.loads((r/'native-frames-corpus.json').read_text())
        frame_tests=json.loads((r/'native-frames-tests.json').read_text())
        assert len(packets)==2 and len(frame_tests)==18
        assert all(x['gc_bytes']==0 and x['allocation_control_bytes']>=4096 for x in frame_tests)
        valid=[x for x in frame_tests if x['success']]
        assert len(valid)==10 and all(x['python_full_packet_roundtrip']for x in valid)
        flagged=[x for x in valid if 'flags'in x]
        assert {x['flags']for x in flagged}==set(range(8))
        assert all(x['crc_valid_malformed_rejections']==10 and x['authorization_rejections']==2 for x in flagged)
        assert any(x.get('raw_bytes',0)>262144 and x['frame_compression']==1 for x in valid)
        assert any(x.get('dictionary_bytes')==0 and x['frame_compression']==0 for x in valid)
        for row in packets:
            assert row['events']==audit['holdout_events']and row['native_events']+row['fallback_events']==row['events']
            assert row['native_frames']==653 and row['all_native_packets_python_roundtrip']and row['all_native_pack_gc_bytes']==0
            model='logical_strings'if row['variant']=='raw'else'strings'
            control=next(x for x in tables if x['variant']==row['variant']and x['model']==model)
            assert row['bytes']==row['python_baseline_bytes']==control['bytes']['dict32']and row['byte_delta_vs_python']==0
            assert abs(row['B_event']-row['bytes']/row['events'])<1e-12
        checks['CSharp_full_M7_packet_host_zeroGC']='PASS; pretyped input, not full SDK'
        checks['CSharp_full_real_corpus_packet_roundtrip']='PASS; 653 packets per raw/clean variant,200 fallback events paid'
        checks['Unity_M7_framing']='NOT_MEASURED'
        checks['Go_M7_framing']='NOT_IMPLEMENTED; existing Go parity is raw columns only'
    if (r/'go-frames.json').exists():
        go_frames=json.loads((r/'go-frames.json').read_text())
        assert go_frames['decoded_packets']==1316 and go_frames['decoded_events']==128787 and go_frames['rejected_packets']==112
        assert go_frames['all_source_typed_values_equal']and go_frames['signed_zero_and_decimal_lexemes_preserved']
        checks['Go_M7_framing']='PASS; independent catalog/alias-based offline decoder, no fixture row hints'
        checks['Go_HTTP_persistence_ACK']='NOT_IMPLEMENTED'
    if (r/'cross-benchmark.json').exists():
        cross=json.loads((r/'cross-benchmark.json').read_text())
        assert [x['variant']for x in cross]==['raw','all_clean']
        for row in cross:
            assert row['events']==audit['holdout_events']and row['max_previous_signed_columns']==16
            model='logical_strings'if row['variant']=='raw'else'strings'
            control=next(x for x in tables if x['variant']==row['variant']and x['model']==model)
            for size,total in row['estimated_frame_bytes'].items():
                assert abs(row['estimated_frame_B_event'][size]-total/row['events'])<1e-12
                assert row['baseline_bytes'][size]==control['bytes'][f'dict{int(size)//1024}']
            assert row['mode_column_counts']['5']>0 and row['mode_column_counts']['6']>0
        checks['experimental_cross_scope']='RAW_COLUMNS_ONLY; estimated framing allowance; NOT_MAIN_M7_NATIVE_UNITY'
    if (r/'unity-editor.json').exists()and(r/'unity-android.json').exists():
        from verify_unity7 import run as verify_unity
        verify_unity()
        for name in ('unity-editor','unity-android'):
            unity=json.loads((r/(name+'.json')).read_text())
            assert unity['allocation_control_samples']>0 and unity['empty_control_samples']==0
            expected_count=12+(4 if (r/'native-tables.json').exists()else 0)
            assert unity['allocation_measurement_valid'] and len(unity['measurements'])==expected_count
            assert all(row['gc_alloc_samples']==row['gc_bytes']==0 and row['raw_parity']for row in unity['measurements'])
        android=json.loads((r/'unity-android.json').read_text())
        assert android['scripting_backend']=='IL2CPP'and android['qemu']=='1'and not android['physical_phone']
        checks['Unity_Editor_pretyped_stage_zeroGC']='PASS'
        checks['Unity_Android_IL2CPP_pretyped_stage_zeroGC']='PASS'
        if (r/'native-tables.json').exists():
            for name in ('unity-editor','unity-android','unity-android-16k'):
                result=json.loads((r/(name+'.json')).read_text())
                assert len([x for x in result['measurements']if x.get('string_model')])==4
            checks['string_candidate_Unity_CPU_GC']='SCOPED_STRING_STAGE_ZERO_GC_PARITY_PASS; not physical phone/full SDK'
            checks['table_candidate_Unity_CPU_GC']='STRING_STAGE_PASS; metadata flag16 NOT_PORTED'
        checks['Unity_IL2CPP_zeroGC']='NOT_MEASURED_FOR_FULL_SDK_INGRESS_FRAMING_DELIVERY'
        checks['android_emulator_encode100_max_mean_ms']=max(row['mean_ms']for row in android['measurements']if row['events']==100)
        checks['phone_5ms']='NOT_MEASURED_ON_PHYSICAL_PHONE'
        if (r/'unity-android-16k.json').exists():
            aligned=json.loads((r/'unity-android-16k.json').read_text());assert aligned['page_size']==16384
            checks['Android_IL2CPP_16KB_zeroGC_raw_parity']='PASS'
            checks['android_16KB_emulator_encode100_max_mean_ms']=max(row['mean_ms']for row in aligned['measurements']if row['events']==100)
    (r/'verification.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
if __name__=='__main__':run()
