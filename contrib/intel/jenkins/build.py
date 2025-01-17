import os
import sys

# add jenkins config location to PATH
sys.path.append(f"{os.environ['WORKSPACE']}/ci_resources/configs/{os.environ['CLUSTER']}")
import cloudbees_config

import argparse
import subprocess
import shlex
import common
import re
import shutil

def build_libfabric(libfab_install_path, mode, cluster=None, ucx=None):

	if (os.path.exists(libfab_install_path) != True):
		os.makedirs(libfab_install_path)

	config_cmd = ['./configure', f'--prefix={libfab_install_path}']
	enable_prov_val = 'yes'

	if (mode == 'dbg'):
		config_cmd.append('--enable-debug')
	elif (mode == 'dl'):
		enable_prov_val='dl'

	if (cluster == 'daos'):
		prov_list = common.daos_prov_list
	elif (cluster == 'gpu'):
		prov_list = common.gpu_prov_list
	else:
		prov_list = common.default_prov_list

	for prov in prov_list:
		if (ucx):
			config_cmd.append('--enable-ucx=yes')
			break
		else:
			config_cmd.append(f'--enable-{prov}={enable_prov_val}')

	for op in common.common_disable_list:
		config_cmd.append(f'--enable-{op}=no')

	if (cluster == 'default' and build_item != 'libfabric_mpich' and not ucx):
		for op in common.default_enable_list:
			config_cmd.append(f'--enable-{op}')

	common.run_command(['./autogen.sh'])
	common.run_command(shlex.split(" ".join(config_cmd)))
	common.run_command(['make','clean'])
	common.run_command(['make', '-j32'])
	common.run_command(['make','install'])


def build_fabtests(libfab_install_path, mode):

	os.chdir(f'{workspace}/fabtests')
	if (mode == 'dbg'):
		config_cmd = ['./configure', '--enable-debug',
					  f'--prefix={libfab_install_path}',
					  f'--with-libfabric={libfab_install_path}']
	else:
		config_cmd = ['./configure', f'--prefix={libfab_install_path}',
					  f'--with-libfabric={libfab_install_path}']

	common.run_command(['./autogen.sh'])
	common.run_command(config_cmd)
	common.run_command(['make','clean'])
	common.run_command(['make', '-j32'])
	common.run_command(['make', 'install'])

def extract_mpich(mpitype):

	dest = f'{install_path}/middlewares/{mpitype}_mpichtest'
	if (mpitype == 'mpich'):
		src_dir = 'mpich'
		mpich_tar = cloudbees_config.mpich_tar 
	elif (mpitype == 'impi'):
		src_dir = 'impi_mpichtest'
		mpich_tar = cloudbees_config.impi_mpichtest_tar
	else:
		print(f"Invalid mpi type {mpitype}")
		sys.exit(-1)

	cwd = os.getcwd()
	if (os.path.exists(dest)):
		shutil.rmtree(dest)
	os.makedirs(f'{dest}/{mpitype}_mpichsuite')
	os.chdir(f'{cloudbees_config.scm_dir}/{src_dir}/')
	common.run_command(['tar', '-xvf', 
			f"{cloudbees_config.scm_dir}/{src_dir}/{mpich_tar}",
			'-C', f'{dest}/{mpitype}_mpichsuite', 
			'--strip-components', '1'])
	os.chdir(cwd)

def build_mpich(libfab_installpath_mpich):
	mpich_build_dir = f'{install_path}/middlewares/mpich_mpichtest'
	mpich_path = f"{mpich_build_dir}/mpich_mpichsuite"
	cwd = os.getcwd()
	if (os.path.exists(f"{mpich_build_dir}/bin") !=True):
		print("configure mpich")
		os.chdir(mpich_path)
		configure_cmd = f"./configure "
		configure_cmd += f"--prefix={mpich_build_dir} "
		configure_cmd += f"--with-libfabric={libfab_installpath_mpich} "
		configure_cmd += "--disable-oshmem "
		configure_cmd += "--disable-fortran "
		configure_cmd += "--without-ch4-shmmods "
		configure_cmd += "--with-device=ch4:ofi "
		configure_cmd += "--without-ze "
		print(configure_cmd)
		common.run_command(['./autogen.sh'])
		common.run_command(shlex.split(configure_cmd))
		common.run_command(['make','-j'])
		common.run_command(['make','install'])
		os.chdir(cwd)

def copy_build_dir(install_path):
	middlewares_path = f'{install_path}/middlewares'
	if (os.path.exists(middlewares_path) != True):
		os.makedirs(f'{install_path}/middlewares')

	shutil.copytree(f'{cloudbees_config.build_dir}/shmem',
					f'{middlewares_path}/shmem')
	shutil.copytree(f'{cloudbees_config.build_dir}/oneccl',
					f'{middlewares_path}/oneccl')
	
	os.symlink(f'{cloudbees_config.build_dir}/mpich',
			   f'{middlewares_path}/mpich')
	os.symlink(f'{cloudbees_config.build_dir}/impi',
			   f'{middlewares_path}/impi')
	os.symlink(f'{cloudbees_config.build_dir}/ompi',
			   f'{middlewares_path}/ompi')
	os.symlink(f'{cloudbees_config.build_dir}/oneccl_gpu',
			   f'{middlewares_path}/oneccl_gpu')

def copy_file(file_name):
	if (os.path.exists(f'{workspace}/{file_name}')):
		shutil.copyfile(f'{workspace}/{file_name}',
						f'{install_path}/log_dir/{file_name}')

def log_dir(install_path, release=False):
	if (os.path.exists(f'{install_path}/log_dir') != True):
		os.makedirs(f'{install_path}/log_dir')

	if (release):
		copy_file('Makefile.am.diff')
		copy_file('configure.ac.diff')
		copy_file('release_num.txt')

if __name__ == "__main__":
#read Jenkins environment variables
	# In Jenkins,  JOB_NAME  = 'ofi_libfabric/master' vs BRANCH_NAME = 'master'
	# job name is better to use to distinguish between builds of different
	# jobs but with same branch name.
	jobname = os.environ['JOB_NAME']
	buildno = os.environ['BUILD_NUMBER']
	workspace = os.environ['WORKSPACE']

	parser = argparse.ArgumentParser()
	parser.add_argument('--build_item', help="build libfabric or fabtests", \
						choices=['libfabric', 'libfabric_mpich', 'fabtests', \
								 'builddir', 'logdir', 'extract_mpich', \
								 'extract_impi_mpich', 'mpich'])
	parser.add_argument('--ofi_build_mode', help="select buildmode libfabric "\
						"build mode", choices=['reg', 'dbg', 'dl'])
	parser.add_argument('--build_cluster', help="build libfabric on specified cluster", \
						choices=['daos', 'gpu'], default='default')
	parser.add_argument('--release', help="This job is likely testing a "\
						"release and will be checked into a git tree.",
						action='store_true')
	parser.add_argument('--ucx', help="build with ucx", default=False, \
						action='store_true')

	args = parser.parse_args()
	build_item = args.build_item
	cluster = args.build_cluster
	release = args.release
	ucx = args.ucx

	if (args.ofi_build_mode):
		ofi_build_mode = args.ofi_build_mode
	else:
		ofi_build_mode = 'reg'

	install_path = f'{cloudbees_config.install_dir}/{jobname}/{buildno}'
	libfab_install_path = f'{cloudbees_config.install_dir}/{jobname}/{buildno}/{ofi_build_mode}'

	if (ucx):
		libfab_install_path += '/ucx'
		workspace += '/ucx'

	p = re.compile('mpi*')

	if (build_item == 'libfabric'):
			build_libfabric(libfab_install_path, ofi_build_mode, cluster, ucx)
	elif (build_item == 'libfabric_mpich'):
			build_libfabric(f'{libfab_install_path}/libfabric_mpich',
							ofi_build_mode, cluster)
	elif (build_item == 'mpich'):
		build_mpich(f'{libfab_install_path}/libfabric_mpich')
	elif (build_item == 'fabtests'):
		build_fabtests(libfab_install_path, ofi_build_mode)
	elif (build_item == 'extract_mpich'):
		extract_mpich('mpich')
	elif (build_item == 'extract_impi_mpich'):
		extract_mpich('impi')
	elif (build_item == 'builddir'):
		copy_build_dir(install_path)
	elif (build_item == 'logdir'):
		log_dir(install_path, release)
