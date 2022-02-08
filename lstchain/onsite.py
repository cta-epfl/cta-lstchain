from pathlib import Path

from .paths import parse_calibration_name

DEFAULT_BASE_PATH = Path('/fefs/aswg/data/real')
DEFAULT_R0_PATH = DEFAULT_BASE_PATH / 'R0'


def create_pro_symlink(output_dir):
    '''Create or update the pro symlink to given ``output dir``'''
    output_dir = Path(output_dir).expanduser().resolve()
    pro_dir = output_dir.parent / "pro"

    # remove previous pro link, if it points to an older version
    if pro_dir.exists() and pro_dir.resolve() != output_dir.resolve():
        pro_dir.unlink()

    if not pro_dir.exists():
        pro_dir.symlink_to(output_dir)


def find_r0_subrun(run, sub_run, r0_dir=DEFAULT_R0_PATH):
    '''
    Find the given subrun R0 file (i.e. globbing for the date part)
    '''
    file_list = sorted(r0_dir.rglob(f'LST-1.1.Run{run:05d}.{sub_run:04d}*.fits.fz'))

    if len(file_list) == 0:
        raise IOError(f"Run {run} not found\n")
    else:
        return file_list[0]


def find_pedestal_file(pro, pedestal_run=None, date=None, base_dir=DEFAULT_BASE_PATH):
    # pedestal base dir
    ped_dir = Path(base_dir) / "monitoring/PixelCalibration/LevelA/drs4_baseline"

    if pedestal_run is None and date is None:
        raise ValueError('Must give at least `date` or `run`')

    if pedestal_run is not None:
        # search a specific pedestal run
        file_list = sorted(ped_dir.rglob(f'{pro}/drs4_pedestal.Run{pedestal_run:05d}.0000.h5'))

        if len(file_list) == 0:
            raise IOError(f"Pedestal file from run {pedestal_run} not found\n")

        return file_list[0].resolve()

    # search for a unique pedestal file from the same date
    file_list = sorted((ped_dir / date / pro).glob('drs4_pedestal*.0000.h5'))
    if len(file_list) == 0:
        raise IOError(f"No pedestal file found for date {date}")

    if len(file_list) > 1:
        raise IOError(f"Too many pedestal files found for date {date}: {file_list}, choose one run\n")

    return file_list[0].resolve()


def find_run_summary(date, base_dir=DEFAULT_BASE_PATH):
    run_summary_path = base_dir / f"monitoring/RunSummary/RunSummary_{date}.ecsv"
    if not run_summary_path.exists():
        raise IOError(f"Night summary file {run_summary_path} does not exist\n")
    return run_summary_path


def find_time_calibration_file(pro, run, time_run=None, base_dir=DEFAULT_BASE_PATH):
    '''Find a time calibration file for given run
    '''

    # search for time calibration file
    time_file = None

    time_dir = Path(base_dir) / "monitoring/PixelCalibration/LevelA/drs4_time_sampling_from_FF"

    # search the last time run before or equal to the calibration run
    if time_run is None:
        file_list = sorted(time_dir.rglob(f'*/{pro}/time_calibration.Run*.0000.h5'))

        if len(file_list) == 0:
            raise IOError(f"No time calibration file found in the data tree for prod {pro}\n")

        for path in file_list:
            run_in_list = parse_calibration_name(path)
            if run_in_list.run <= run:
                time_file = path.resolve()
            else:
                break

        if time_file is None:
            raise IOError(f"No time calibration file found before run {run} for prod {pro}\n")

        return time_file

    # if given, search a specific time file
    file_list = sorted(time_dir.rglob(f'*/{pro}/time_calibration.Run{time_run:05d}.0000.h5'))
    if len(file_list) == 0:
        raise IOError(f"Time calibration file from run {time_run} not found\n")

    return file_list[0].resolve()
