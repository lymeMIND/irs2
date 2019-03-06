from sqlalchemy import create_engine
import os
import time
import datetime
import argparse




def entry_point_features_count(pg_conn,project_name,pipeline_id,task_id,next_task_id,run_dry=True,resetquery=True,one_sample=True):

    select_option_task = 'SELECT option_name,option_value FROM option INNER JOIN task ON option.task_id = task.task_id WHERE task.task_id=%d;'
    select_info_task='SELECT path,command, output_directory, table_name FROM task WHERE task_id=%d'

    query            = select_option_task % task_id
    options          = pg_conn.execute(query).fetchall()
    options_test     =   {c.option_name:c.option_value for c in options}
    options_template =' '.join(option+' ' + options_test[option] for option in options_test)


    query = select_info_task % (task_id)
    results_task_query = pg_conn.execute(query).fetchall()


    path_value  = results_task_query[0][0]
    command     = results_task_query[0][1]
    output_directory    = results_task_query[0][2]
    current_table_name = results_task_query[0][3]

    if(next_task_id != -1):
        print(current_table_name)
        query = select_info_task % (next_task_id)
        results_task_query = pg_conn.execute(query).fetchall()
        next_table_name = results_task_query[0][3]
        print(next_table_name)
        step_features_count(pg_conn, pipeline_id,task_id,next_task_id,current_table_name, path_value,command,output_directory,run_dry,resetquery,one_sample)
        #call the right function here!
    else:
        print('LAST step')
        step_features_count(pg_conn, pipeline_id,task_id,current_table_name,path_value,command,output_directory,run_dry,resetquery,one_sample)





def step_features_count(pg_conn,pipeline_id,task_id,table_name,path_value,command,output_folder, run_dry=True,resetquery=True,one_sample=True):

#to check
    select_option_features_count ='SELECT option_name,option_value FROM option INNER JOIN task ON option.task_id = task.task_id WHERE task.task_id=%d;'

##queries
    sample_selection        = 'SELECT Distinct sample_id, dir_input,filename_input,trimmed_quality, file_extension '\
                          'FROM %s '\
                          'WHERE pipeline_id=%d AND status=\'%s\' AND task_id=\'%s\' ORDER BY sample_id LIMIT 1'
    sample_update_process       = 'UPDATE %s SET status=\'%s\' '\
                                'WHERE  pipeline_id=%d AND sample_id=\'%s\' AND filename_input=\'%s\' AND task_id=%d'


    sample_update_finish_process = 'UPDATE %s SET status=\'%s\', date=\'%s\' , run_time=\'%s\',dir_output=\'%s\''\
                                  'WHERE  pipeline_id=%d AND sample_id=\'%s\' AND filename_input=\'%s\' AND task_id=%d'

    output_id = ['transcriptID','geneID', 'exondID']

    options_template ={}
    for ii in range(0,3):
        task_id_tmp = task_id + ii
        query= select_option_features_count % (task_id_tmp)
        options=pg_conn.execute(query).fetchall()
        options_test={c.option_name:c.option_value for c in options}
        options_tmp =' '.join(option+' ' + options_test[option] for option in options_test)
        options_template[task_id_tmp] = options_tmp

    task_program    = '{path_value}/{command}'.format(path_value=path_value,command=command)
    status = 'pending'
    query = sample_selection %(table_name,pipeline_id, status,task_id)
    samples = pg_conn.execute(query).fetchall()

    while(len(samples) > 0):
        sample = samples[0]

        sample_id       = sample[0]
        dir_input       = sample[1]
        filename_input  = sample[2]
        trimmed_quality = sample[3]
        file_extension  = sample[4]

        samplefile = '{dirinput}/{filename_input}'.format(dirinput=dir_input,filename_input=filename_input)
        if(file_extension == 'bai'):
            samplefile=samplefile.replace('bai','bam')
        elif(samplefile.split('.')[-1] == 'bam'):
            print('nothing to change')
        else:
            print('ERROR UNKNOWN EXTENSION FILE')
            exit()

        if(trimmed_quality == 0):
            dir_output='{}/{}'.format(output_folder, sample_id)
        else:
            dir_output='{}/{}_trimmed_q{}'.format(output_folder,sample_id ,trimmed_quality)

        if(not os.path.exists(dir_output)):
            try:
                os.mkdir(dir_output)
            except OSError:
                print ("Creation of the directory %s failed" % dir_output)
            else:
                print ("Successfully created the directory %s " % dir_output)
        else:
            print('Directory:%s ALREADY EXIST' % dir_output)

        query=sample_update_process % (table_name,'running',pipeline_id,sample_id, filename_input,task_id)
        if(run_dry):
            print(query)
        else:
            pg_conn.execute(query)

        start_time = time.time()
        for ii,key in enumerate(output_id):
            print('########')
            print('STEP %d' % ii)
            task_id_tmp = task_id + ii
            full_filename_output = '{}/{}_{}'.format(dir_output,sample_id, output_id[ii])
            sample2run = ' '.join([task_program, options_template[task_id_tmp]])
            options_change  = '-o {output} {input} '.format(output=full_filename_output,input=samplefile)

            output_log='> {}/step{}.txt'.format(dir_output,ii)
            sample2run=' '.join([sample2run, options_change,output_log])
            print(sample2run)

            if(not run_dry):
                os.system(sample2run)

        elapse=time.time() - start_time
        print(elapse)
        date=datetime.datetime.today().strftime('%Y-%m-%d')

        status = 'done'
        query_update= sample_update_finish_process % (table_name,status,date,int(elapse),dir_output,pipeline_id,sample_id, filename_input,task_id)
        status = 'pending'
        query_check = sample_selection % (table_name,pipeline_id, status,task_id)

        if(run_dry):
            print(query_update)
            print(query_check)
        else:
            pg_conn.execute(query_update)
            samples = pg_conn.execute(query_check).fetchall()

        if(one_sample):
            break



    if(resetquery == True):
        status = 'pending'
        samples_update_process = 'UPDATE %s SET status=\'%s\' WHERE pipeline_id=%d AND task_id=%d' %(table_name,status,pipeline_id,task_id)
        print(samples_update_process)
        pg_conn.execute(samples_update_process)
    #I COULD RUN A NEW TASK HERE FOR PICARD


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True ,help=' in which project fecth samples ')
    parser.add_argument('--pipeline', required=True ,help='which pipeline to run')
    parser.add_argument('--task',required=True ,help='current task to run')
    parser.add_argument('--next_task',required=True ,help='next task to run')

    args = parser.parse_args()
    project = args.project
    pipeline_id= int(args.pipeline)
    task_id = int(args.task)
    next_task_id = int(args.next_task)
##Database connection
    pg_user             = os.environ.get('DB_USER_LYME')
    pg_password         = os.environ['DB_PASSWORD_LYME']
    pg_host             = os.environ['DB_HOST_LYME']
    pg_conn_str         = 'postgresql://' + pg_user + ':' + pg_password + '@' + pg_host + ':5432/rnaseq_manager'
    pg_conn             = create_engine(pg_conn_str, echo=False, paramstyle='format', pool_recycle=1800)

    entry_point_features_count(pg_conn,project,pipeline_id,task_id,next_task_id,run_dry=False,resetquery=True,one_sample=True)

