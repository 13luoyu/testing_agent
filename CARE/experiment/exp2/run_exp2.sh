conda activate qwen
cd ../../qwen3_service
nohup bash qwen3_service.sh >run.log &
sleep 30

conda activate testcase-reuse
cd ../experiment/exp2
python generate_testcase_no_requirement.py
python generate_testcase_no_scenario.py
python generate_testcase_directly.py
python generate_testcase_no_change_impact_analysis.py
python generate_testcase_ESIM.py
python generate_testcase_RPTSP.py

# Do not run all at once to avoid memory overflow
# bash run_compute_acc.sh
# bash run_compute_bsc.sh
# bash run_compute_changed_rule_req_sce.sh
# bash run_compute_reuse.sh
# bash run_compute_testsuite_acc.sh