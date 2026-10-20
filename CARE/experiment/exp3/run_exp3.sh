conda activate qwen
cd ../../qwen3_service
nohup bash qwen3_service.sh >run.log &
sleep 30

cd ../experiment/exp2
conda activate testcase-reuse

python generate_result_ours.py

bash run_compute_acc.sh
bash run_compute_bsc.sh
bash run_compute_reuse.sh
bash run_compute_testsuite_acc.sh