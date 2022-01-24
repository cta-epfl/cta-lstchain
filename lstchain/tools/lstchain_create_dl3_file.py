"""
Create DL3 FITS file from given data DL2 file,
selection cuts and/or IRF FITS files.

Change the selection parameters as need be using the aliases.
The default values are written in the EventSelector and DL3FixedCuts Component
and also given in some example configs in docs/examples/

To use a separate config file for providing the selection parameters,
copy and append the relevant example config files, into a custom config file.
"""

from astropy.io import fits
from astropy.table import QTable
from astropy.coordinates import SkyCoord
from astropy.io import fits
from ctapipe.core import (
    Provenance,
    Tool,
    ToolConfigurationError,
    traits,
)

from lstchain.io import EventSelector, DL3FixedCuts
from lstchain.io import read_data_dl2_to_QTable
from lstchain.irf import (
    add_icrs_position_params,
    create_event_list,
)
from lstchain.paths import (
    dl2_to_dl3_filename,
    run_info_from_filename,
)
from lstchain.reco.utils import get_effective_time
from lstchain.paths import run_info_from_filename, dl2_to_dl3_filename
from lstchain.irf import create_event_list, add_icrs_position_params
from lstchain.io import EventSelector, DL3FixedCuts, DataBinning


__all__ = ["DataReductionFITSWriter"]


class DataReductionFITSWriter(Tool):
    name = "DataReductionFITSWriter"
    description = __doc__
    example = """
    To generate DL3 file from an observed data DL2 file, using default cuts:
    > lstchain_create_dl3_file
        -d /path/to/DL2_data_file.h5
        -o /path/to/DL3/file/
        --input-irf /path/to/irf.fits.gz
        --source-name Crab
        --source-ra 83.633deg
        --source-dec 22.01deg

    Or use a config file for the cuts:
    > lstchain_create_dl3_file
        -d /path/to/DL2_data_file.h5
        -o /path/to/DL3/file/
        --input-irf /path/to/irf.fits.gz
        --source-name Crab
        --source-ra 83.633deg
        --source-dec 22.01deg
        --overwrite
        --config /path/to/config.json

    Or pass the selection cuts from command-line:
    > lstchain_create_dl3_file
        -d /path/to/DL2_data_file.h5
        -o /path/to/DL3/file/
        --input-irf /path/to/irf.fits.gz
        --source-name Crab
        --source-ra 83.633deg
        --source-dec 22.01deg
        --fixed-gh-cut 0.9
        --overwrite

    Or pass the selection cuts based on fixed gamma efficiency:
    > lstchain_create_dl3_file
        -d /path/to/DL2_data_file.h5
        -o /path/to/DL3/file/
        --input-irf /path/to/irf.fits.gz
        --source-name Crab
        --source-ra 83.633deg
        --source-dec 22.01deg
        --optimize-gh
        --overwrite
    """

    input_dl2 = traits.Path(
        help="Input data DL2 file",
        exists=True,
        directory_ok=False,
        file_ok=True
    ).tag(config=True)

    output_dl3_path = traits.Path(
        help="DL3 output filedir",
        directory_ok=True,
        file_ok=False
    ).tag(config=True)

    input_irf = traits.Path(
        help="Compressed FITS file of IRFs",
        exists=True,
        directory_ok=False,
        file_ok=True,
    ).tag(config=True)

    source_name = traits.Unicode(
        help="Name of Source"
    ).tag(config=True)

    source_ra = traits.Unicode(
        help="RA position of the source"
    ).tag(config=True)

    source_dec = traits.Unicode(
        help="DEC position of the source"
    ).tag(config=True)

    optimize_gh = traits.Bool(
        help="If true, use a fixed gamma efficiency for optimizing the cuts",
        default_value=False,
    ).tag(config=True)

    overwrite = traits.Bool(
        help="If True, overwrites existing output file without asking",
        default_value=False,
    ).tag(config=True)

    classes = [EventSelector, DL3FixedCuts]

    aliases = {
        ("d", "input-dl2"): "DataReductionFITSWriter.input_dl2",
        ("o", "output-dl3-path"): "DataReductionFITSWriter.output_dl3_path",
        "input-irf": "DataReductionFITSWriter.input_irf",
        "fixed-gh-cut": "DL3FixedCuts.fixed_gh_cut",
        "source-name": "DataReductionFITSWriter.source_name",
        "source-ra": "DataReductionFITSWriter.source_ra",
        "source-dec": "DataReductionFITSWriter.source_dec",
    }

    flags = {
        "overwrite": (
            {"DataReductionFITSWriter": {"overwrite": True}},
            "overwrite output file if True",
        ),
        "optimize-gh": (
            {"DataReductionFITSWriter": {"optimize_gh": True}},
            "Uses cuts optimization",
        ),
    }

    def setup(self):

        self.filename_dl3 = dl2_to_dl3_filename(self.input_dl2)
        self.provenance_log = self.output_dl3_path / (self.name + ".provenance.log")

        Provenance().add_input_file(self.input_dl2)

        self.event_sel = EventSelector(parent=self)
        self.fixed_cuts = DL3FixedCuts(parent=self)
        self.data_bin = DataBinning(parent=self)

        self.output_file = self.output_dl3_path.absolute() / self.filename_dl3
        if self.output_file.exists():
            if self.overwrite:
                self.log.warning(f"Overwriting {self.output_file}")
                self.output_file.unlink()
            else:
                raise ToolConfigurationError(
                    f"Output file {self.output_file} already exists,"
                    " use --overwrite to overwrite"
                )
        if not (self.source_ra or self.source_dec):
            self.source_pos = SkyCoord.from_name(self.source_name)
        elif bool(self.source_ra) != bool(self.source_dec):
            raise ToolConfigurationError(
                "Either provide both RA and DEC values for the source or none"
            )
        else:
            self.source_pos = SkyCoord(ra=self.source_ra, dec=self.source_dec)

        self.log.debug(f"Output DL3 file: {self.output_file}")

        if self.optimize_gh and self.input_irf:
            try:
                QTable.read(self.input_irf, hdu="GH CUTS")
            except KeyError:
                raise ToolConfigurationError(
                    f"{self.input_irf} does not have GH CUTS HDU, or "
                    "does not have energy-dependent gammaness cuts"
                )

    def start(self):

        self.data = read_data_dl2_to_QTable(str(self.input_dl2))
        self.effective_time, self.elapsed_time = get_effective_time(self.data)
        self.run_number = run_info_from_filename(self.input_dl2)[1]

        self.data = self.event_sel.filter_cut(self.data)

        if self.optimize_gh and self.input_irf:
            self.gh_cuts = QTable.read(self.input_irf, hdu="GH CUTS")

            self.data = self.fixed_cuts.apply_opt_gh_cuts(
                self.data, self.gh_cuts
            )
            self.data = add_icrs_position_params(self.data, self.source_pos)
            self.log.info(
                "Using fixed gamma efficiency of " +
                f'{self.gh_cuts.meta["GH_EFF"]}'
            )
        else:
            self.data = self.fixed_cuts.gh_cut(self.data)
            self.data = add_icrs_position_params(self.data, self.source_pos)
            self.log.info(f"Using fixed G/H cut of {self.fixed_cuts.fixed_gh_cut}")

        self.log.info("Generating event list")
        self.events, self.gti, self.pointing = create_event_list(
            data=self.data,
            run_number=self.run_number,
            source_name=self.source_name,
            source_pos=self.source_pos,
            effective_time=self.effective_time.value,
            elapsed_time=self.elapsed_time.value,
        )

        self.hdulist = fits.HDUList(
            [fits.PrimaryHDU(), self.events, self.gti, self.pointing]
        )

        if self.input_irf:
            irf = fits.open(self.input_irf)
            self.log.info("Adding IRF HDUs")

            for irf_hdu in irf[1:]:
                self.hdulist.append(irf_hdu)

    def finish(self):
        self.hdulist.writeto(self.output_file, overwrite=self.overwrite)

        Provenance().add_output_file(self.output_file)


def main():
    tool = DataReductionFITSWriter()
    tool.run()


if __name__ == "__main__":
    main()
