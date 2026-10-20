cd exp1
python generate_result_ours.py
bash run_compute_acc.sh
bash run_compute_bsc.sh
bash run_compute_changed_rule_req_sce.sh
bash run_compute_testsuite_acc.sh
python draw_figure.py
python draw_figure_2.py
cd ..


cd exp2
bash run_compute_reuse_acc.sh
python draw_figure_acc.py
python draw_time_table.py
cd ..


cd exp3
bash run_generate_result_ours.sh
bash run_compute_acc.sh
python draw_figure.py
cd ..