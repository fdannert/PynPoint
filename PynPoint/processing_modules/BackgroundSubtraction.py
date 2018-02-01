"""
Modules with background subtraction routines.
"""

import sys

import numpy as np

from scipy.sparse.linalg import svds
from scipy.optimize import curve_fit

from PynPoint.util.Progress import progress
from PynPoint.core.Processing import ProcessingModule
from PynPoint.processing_modules.BadPixelCleaning import BadPixelCleaningSigmaFilterModule
from PynPoint.processing_modules.SimpleTools import CutAroundPositionModule, CombineTagsModule
from PynPoint.processing_modules.StarAlignment import LocateStarModule


class MeanBackgroundSubtractionModule(ProcessingModule):
    """
    Module for mean background subtraction, only applicable on data with dithering.
    """

    def __init__(self,
                 star_pos_shift=None,
                 cubes_per_position=1,
                 name_in="mean_background_subtraction",
                 image_in_tag="im_arr",
                 image_out_tag="bg_cleaned_arr"):
        """
        Constructor of MeanBackgroundSubtractionModule.

        :param star_pos_shift: Frame index offset for the background subtraction. Typically equal
                               to the number of frames per dither location. If set to *None*, the
                               (non-static) NFRAMES attributes will be used.
        :type star_pos_shift: int
        :param cubes_per_position: Number of consecutive cubes per dither position.
        :type cubes_per_position: int
        :param name_in: Unique name of the module instance.
        :type name_in: str
        :param image_in_tag: Tag of the database entry that is read as input.
        :type image_in_tag: str
        :param image_out_tag: Tag of the database entry that is written as output. Should be
                              different from *image_in_tag*.
        :type image_out_tag: str

        :return: None
        """

        super(MeanBackgroundSubtractionModule, self).__init__(name_in)

        self.m_image_in_port = self.add_input_port(image_in_tag)
        self.m_image_out_port = self.add_output_port(image_out_tag)

        self.m_star_prs_shift = star_pos_shift
        self.m_cubes_per_position = cubes_per_position

    def run(self):
        """
        Run method of the module. Mean background subtraction which uses either a constant index
        offset or the (non-static) NFRAMES values. The mean background is calculated from the
        cubes before and after the science cube(s).

        :return: None
        """

        # Use NFRAMES values if star_pos_shift is None
        if self.m_star_prs_shift is None:
            self.m_star_prs_shift = self.m_image_in_port.get_attribute("NFRAMES")

        number_of_frames = self.m_image_in_port.get_shape()[0]

        # Check size of the input, only needed when a manual star_pos_shift is provided
        if not isinstance(self.m_star_prs_shift, np.ndarray) and \
               number_of_frames < self.m_star_prs_shift*2.0:
            raise ValueError("The input stack is to small for mean background subtraction. At least"
                             "one star position shift is needed.")

        # Number of substacks
        if isinstance(self.m_star_prs_shift, np.ndarray):
            num_stacks = np.size(self.m_star_prs_shift)
        else:
            num_stacks = int(np.floor(number_of_frames/self.m_star_prs_shift))

        # First mean subtraction to set up the output port array
        if isinstance(self.m_star_prs_shift, np.ndarray):
            next_start = np.sum(self.m_star_prs_shift[0:self.m_cubes_per_position])
            next_end = np.sum(self.m_star_prs_shift[0:2*self.m_cubes_per_position])

            if 2*self.m_cubes_per_position > np.size(self.m_star_prs_shift):
                raise ValueError("Not enough frames available for the background subtraction.")

            # Calculate the mean background of cubes_per_position number of cubes
            tmp_data = self.m_image_in_port[next_start:next_end,]
            tmp_mean = np.mean(tmp_data, axis=0)

        else:
            tmp_data = self.m_image_in_port[self.m_star_prs_shift:2*self.m_star_prs_shift,]
            tmp_mean = np.mean(tmp_data, axis=0)

        # Initiate the result port data with the first frame
        tmp_res = self.m_image_in_port[0,] - tmp_mean

        if self.m_image_in_port.tag == self.m_image_out_port.tag:
            raise NotImplementedError("Same input and output port not implemented yet.")
        else:
            self.m_image_out_port.set_all(tmp_res, data_dim=3)

        print "Subtracting background from stack-part " + str(1) + " of " + \
              str(num_stacks) + " stack-parts"

        # Mean subtraction of the first stack (minus the first frame)
        if isinstance(self.m_star_prs_shift, np.ndarray):
            for i in range(1, self.m_cubes_per_position):
                print "Subtracting background from stack-part " + str(i+1) + " of " + \
                      str(num_stacks) + " stack-parts"

            tmp_data = self.m_image_in_port[1:next_start,]
            tmp_data = tmp_data - tmp_mean

            self.m_image_out_port.append(tmp_data)

        else:
            tmp_data = self.m_image_in_port[1:self.m_star_prs_shift, :, :]
            tmp_data = tmp_data - tmp_mean

            # TODO This will not work for same in and out port
            self.m_image_out_port.append(tmp_data)

        # Processing of the rest of the data
        if isinstance(self.m_star_prs_shift, np.ndarray):
            for i in range(self.m_cubes_per_position, num_stacks, self.m_cubes_per_position):
                prev_start = np.sum(self.m_star_prs_shift[0:i-self.m_cubes_per_position])
                prev_end = np.sum(self.m_star_prs_shift[0:i])

                next_start = np.sum(self.m_star_prs_shift[0:i+self.m_cubes_per_position])
                next_end = np.sum(self.m_star_prs_shift[0:i+2*self.m_cubes_per_position])

                for j in range(self.m_cubes_per_position):
                    print "Subtracting background from stack-part " + str(i+j+1) + " of " + \
                          str(num_stacks) + " stack-parts"

                # calc the mean (previous)
                tmp_data = self.m_image_in_port[prev_start:prev_end,]
                tmp_mean = np.mean(tmp_data, axis=0)

                if i < num_stacks-self.m_cubes_per_position:
                    # calc the mean (next)
                    tmp_data = self.m_image_in_port[next_start:next_end,]
                    tmp_mean = (tmp_mean + np.mean(tmp_data, axis=0)) / 2.0

                # subtract mean
                tmp_data = self.m_image_in_port[prev_end:next_start,]
                tmp_data = tmp_data - tmp_mean
                self.m_image_out_port.append(tmp_data)

        else:
            # the last and the one before will be performed afterwards
            top = int(np.ceil(number_of_frames /
                              self.m_star_prs_shift)) - 2

            for i in range(1, top, 1):
                print "Subtracting background from stack-part " + str(i+1) + " of " + \
                      str(num_stacks) + " stack-parts"
                # calc the mean (next)
                tmp_data = self.m_image_in_port[(i+1) * self.m_star_prs_shift:
                                                (i+2) * self.m_star_prs_shift,
                                                :, :]
                tmp_mean = np.mean(tmp_data, axis=0)
                # calc the mean (previous)
                tmp_data = self.m_image_in_port[(i-1) * self.m_star_prs_shift:
                                                (i+0) * self.m_star_prs_shift, :, :]
                tmp_mean = (tmp_mean + np.mean(tmp_data, axis=0)) / 2.0

                # subtract mean
                tmp_data = self.m_image_in_port[(i+0) * self.m_star_prs_shift:
                                                (i+1) * self.m_star_prs_shift, :, :]
                tmp_data = tmp_data - tmp_mean
                self.m_image_out_port.append(tmp_data)

            # last and the one before
            # 1. ------------------------------- one before -------------------
            # calc the mean (previous)
            print "Subtracting background from stack-part " + str(top+1) + " of " + \
                  str(num_stacks) + " stack-parts"
            tmp_data = self.m_image_in_port[(top - 1) * self.m_star_prs_shift:
                                            (top + 0) * self.m_star_prs_shift, :, :]
            tmp_mean = np.mean(tmp_data, axis=0)
            # calc the mean (next)
            # "number_of_frames" is important if the last step is to huge
            tmp_data = self.m_image_in_port[(top + 1) * self.m_star_prs_shift:
                                            number_of_frames, :, :]

            tmp_mean = (tmp_mean + np.mean(tmp_data, axis=0)) / 2.0

            # subtract mean
            tmp_data = self.m_image_in_port[top * self.m_star_prs_shift:
                                            (top + 1) * self.m_star_prs_shift, :, :]
            tmp_data = tmp_data - tmp_mean
            self.m_image_out_port.append(tmp_data)

            # 2. ------------------------------- last -------------------
            # calc the mean (previous)
            print "Subtracting background from stack-part " + str(top+2) + " of " + \
                  str(num_stacks) + " stack-parts"
            tmp_data = self.m_image_in_port[(top + 0) * self.m_star_prs_shift:
                                            (top + 1) * self.m_star_prs_shift, :, :]
            tmp_mean = np.mean(tmp_data, axis=0)

            # subtract mean
            tmp_data = self.m_image_in_port[(top + 1) * self.m_star_prs_shift:
                                            number_of_frames, :, :]
            tmp_data = tmp_data - tmp_mean
            self.m_image_out_port.append(tmp_data)
            # -----------------------------------------------------------

        self.m_image_out_port.copy_attributes_from_input_port(self.m_image_in_port)

        self.m_image_out_port.add_history_information("Background",
                                                      "mean subtraction")

        self.m_image_out_port.close_port()


class SimpleBackgroundSubtractionModule(ProcessingModule):
    """
    Module for simple background subtraction, only applicable for dithered data.
    """

    def __init__(self,
                 star_pos_shift,
                 name_in="background_subtraction",
                 image_in_tag="im_arr",
                 image_out_tag="bg_cleaned_arr"):
        """
        Constructor of SimpleBackgroundSubtractionModule.

        :param star_pos_shift: Frame index offset for the background subtraction. Typically equal
                               to the number of frames per dither location.
        :type star_pos_shift: int
        :param name_in: Unique name of the module instance.
        :type name_in: str
        :param image_in_tag: Tag of the database entry that is read as input.
        :type image_in_tag: str
        :param image_out_tag: Tag of the database entry that is written as output.
        :type image_out_tag: str

        :return: None
        """

        super(SimpleBackgroundSubtractionModule, self).__init__(name_in)

        # add Ports
        self.m_image_in_port = self.add_input_port(image_in_tag)
        self.m_image_out_port = self.add_output_port(image_out_tag)

        self.m_star_prs_shift = star_pos_shift

    def run(self):
        """
        Run method of the module. Simple background subtraction which uses either a constant
        index offset.

        :return: None
        """

        number_of_frames = self.m_image_in_port.get_shape()[0]

        # first subtraction is used to set up the output port array
        tmp_res = self.m_image_in_port[0] - \
                  self.m_image_in_port[(0 + self.m_star_prs_shift) % number_of_frames]

        if self.m_image_in_port.tag == self.m_image_out_port.tag:
            self.m_image_out_port[0] = tmp_res
        else:
            self.m_image_out_port.set_all(tmp_res, data_dim=3)

        # process with the rest of the data
        for i in range(1, number_of_frames):
            tmp_res = self.m_image_in_port[i] - \
                      self.m_image_in_port[(i + self.m_star_prs_shift) % number_of_frames]

            if self.m_image_in_port.tag == self.m_image_out_port.tag:
                self.m_image_out_port[i] = tmp_res
            else:
                self.m_image_out_port.append(tmp_res)

        self.m_image_out_port.copy_attributes_from_input_port(self.m_image_in_port)

        self.m_image_out_port.add_history_information("Background",
                                                      "simple subtraction")

        self.m_image_out_port.close_port()


class PCABackgroundPreparationModule(ProcessingModule):
    """
    Module for preparing the PCA background subtraction.
    """

    def __init__(self,
                 dither,
                 name_in="separate_star",
                 image_in_tag="im_arr",
                 star_out_tag="im_arr_star",
                 background_out_tag="im_arr_background"):
        """
        Constructor of PCABackgroundPreparationModule.

        :param dither: Tuple with the parameters for separating the star and background frames.
                       The tuple should contain three values (dither_positions, cubes_per_position,
                       first_star_cube) with *dither_positions* the number of unique dither
                       locations on the detector, *cubes_per_position* the number of consecutive
                       cubes per dither position, and *first_star_cube* the index value of the
                       first cube which contains the star (Python indexing starts at zero).
        :type select: tuple
        :param name_in: Unique name of the module instance.
        :type name_in: str
        :param image_in_tag: Tag of the database entry that is read as input.
        :type image_in_tag: str
        :param star_out_tag: Tag of the database entry with frames that include the star. Should be
                             different from *image_in_tag*.
        :type star_out_tag: str
        :param background_out_tag: Tag of the the database entry with frames that contain only
                                   background and no star. Should be different from *image_in_tag*.
        :type background_out_tag: str

        :return: None
        """

        super(PCABackgroundPreparationModule, self).__init__(name_in)

        self.m_image_in_port = self.add_input_port(image_in_tag)
        self.m_star_out_port = self.add_output_port(star_out_tag)
        self.m_background_out_port = self.add_output_port(background_out_tag)

        if len(dither) != 3:
            raise ValueError("The 'dither' tuple should contain three integer values.")

        self.m_dither_positions = dither[0]
        self.m_cubes_per_position = dither[1]
        self.m_first_star_cube = dither[2]

        self.m_star_out_tag = star_out_tag

    def run(self):
        """
        Run method of the module. Separates the star and background frames, subtracts the mean
        background from both the star and background frames, writes the star and background
        frames separately, and locates the star in each frame (required for the masking in the
        PCA background module).

        :return: None
        """

        if "NEW_PARA" not in self.m_image_in_port.get_all_non_static_attributes():
            raise ValueError("NEW_PARA not found in header. Parallactic angles should be "
                             "provided for all frames before PCA background subtraction.")

        parang = self.m_image_in_port.get_attribute("NEW_PARA")
        nframes = self.m_image_in_port.get_attribute("NFRAMES")

        cube_mean = np.zeros((nframes.shape[0], self.m_image_in_port.get_shape()[2], \
                             self.m_image_in_port.get_shape()[1]))

        # Mean of each cube
        count = 0
        for i, item in enumerate(nframes):
            cube_mean[i,] = np.mean(self.m_image_in_port[count:count+item,], axis=0)
            count += item

        # Flag star and background cubes
        bg_frames = np.ones(nframes.shape[0], dtype=bool)
        for i in range(self.m_first_star_cube, np.size(nframes), \
                       self.m_cubes_per_position*self.m_dither_positions):
            bg_frames[i:i+self.m_cubes_per_position] = False

        bg_indices = np.nonzero(bg_frames)[0]

        star_init = False
        background_init = False

        star_parang = np.empty(0)
        star_nframes = np.empty(0)

        background_parang = np.empty(0)
        background_nframes = np.empty(0)

        num_frames = self.m_image_in_port.get_shape()[0]

        # Separate star and background cubes, and subtract mean background
        count = 0
        for i, item in enumerate(nframes):
            progress(i, len(nframes), "Running PCABackgroundPreparationModule...")

            im_tmp = self.m_image_in_port[count:count+item,]

            # Background frames
            if bg_frames[i]:
                # Mean background of the cube
                background = cube_mean[i,]

                # Subtract mean background, save data, and select corresponding NEW_PARA and NFRAMES
                if background_init:
                    self.m_background_out_port.append(im_tmp-background)

                    background_parang = np.append(background_parang, parang[count:count+item])
                    background_nframes = np.append(background_nframes, nframes[i])

                else:
                    self.m_background_out_port.set_all(im_tmp-background)

                    background_parang = parang[count:count+item]
                    background_nframes = np.zeros(1, dtype=np.int64)
                    background_nframes[0] = nframes[i]

                    background_init = True

            # Star frames
            else:

                # Previous background cube
                if np.size(bg_indices[bg_indices < i]) > 0:
                    index_prev = np.amax(bg_indices[bg_indices < i])
                    bg_prev = cube_mean[index_prev,]

                # Next background cube
                if np.size(bg_indices[bg_indices > i]) > 0:
                    index_next = np.amin(bg_indices[bg_indices > i])
                    bg_next = cube_mean[index_next,]

                # Select background: previous, next, or mean of previous and next
                if i == 0:
                    background = bg_next

                elif i == np.size(nframes)-1:
                    background = bg_prev

                else:
                    background = (bg_prev+bg_next)/2.

                # Subtract mean background, save data, and select corresponding NEW_PARA and NFRAMES
                if star_init:
                    self.m_star_out_port.append(im_tmp-background)

                    star_parang = np.append(star_parang, parang[count:count+item])
                    star_nframes = np.append(star_nframes, nframes[i])

                else:
                    self.m_star_out_port.set_all(im_tmp-background)

                    star_parang = parang[count:count+item]
                    star_nframes = np.zeros(1, dtype=np.int64)
                    star_nframes[0] = nframes[i]

                    star_init = True

            count += item

        sys.stdout.write("Running PCABackgroundPreparationModule... [DONE]\n")
        sys.stdout.flush()

        # Star - Update attribute

        self.m_star_out_port.copy_attributes_from_input_port(self.m_image_in_port)

        self.m_star_out_port.add_attribute("NEW_PARA", star_parang, static=False)
        self.m_star_out_port.add_attribute("NFRAMES", star_nframes, static=False)

        self.m_star_out_port.add_history_information("Star frames separated",
                                                     str(len(star_parang))+"/"+ \
                                                     str(len(parang))+" cubes")

        # Background - Update attributes

        self.m_background_out_port.copy_attributes_from_input_port(self.m_image_in_port)

        self.m_background_out_port.add_attribute("NEW_PARA", background_parang, static=False)
        self.m_background_out_port.add_attribute("NFRAMES", background_nframes, static=False)

        self.m_background_out_port.add_history_information("Background frames separated",
                                                           str(len(background_parang))+"/"+ \
                                                           str(len(parang))+" cubes")

        # Close database

        self.m_star_out_port.close_port()


class PCABackgroundSubtractionModule(ProcessingModule):
    """
    Module for PCA background subtraction.
    """

    def __init__(self,
                 pca_number=60,
                 mask_radius=0.7,
                 mask_position="mean",
                 name_in="pca_background",
                 star_in_tag="im_star",
                 background_in_tag="im_background",
                 subtracted_out_tag="background_subtracted",
                 residuals_out_tag=None):
        """
        Constructor of PCABackgroundSubtractionModule.

        :param pca_number: Number of principle components.
        :type pca_number: int
        :param mask_radius: Radius of the mask (arcsec).
        :type mask_radius: float
        :param mask_position: Position of the mask uses a single value ("mean") for all frames
                              or an value ("exact") for each frame separately.
        :type mask_position: str
        :param name_in: Unique name of the module instance.
        :type name_in: str
        :param star_in_tag: Tag of the input database entry with star frames.
        :type star_in_tag: str
        :param background_in_tag: Tag of the input database entry with the background frames.
        :type background_in_tag: str
        :param subtracted_out_tag: Tag of the output database entry with the background
                                   subtracted star frames.
        :type subtracted_out_tag: str
        :param residuals_out_tag: Tag of the output database entry with the residuals of the
                                  background subtraction.
        :type residuals_out_tag: str

        :return: None
        """

        super(PCABackgroundSubtractionModule, self).__init__(name_in)

        self.m_star_in_port = self.add_input_port(star_in_tag)
        self.m_background_in_port = self.add_input_port(background_in_tag)
        self.m_subtracted_out_port = self.add_output_port(subtracted_out_tag)
        if residuals_out_tag is not None:
            self.m_residuals_out_port = self.add_output_port(residuals_out_tag)

        self.m_pca_number = pca_number
        self.m_mask_radius = mask_radius
        self.m_mask_position = mask_position
        self.m_residuals_out_tag = residuals_out_tag

    def _create_mask(self, mask_radius, star_position, num_frames):
        """
        Method for creating a circular mask at the star position.
        """

        im_dim = self.m_star_in_port[0,].shape

        x_grid = np.arange(0, im_dim[0], 1)
        y_grid = np.arange(0, im_dim[1], 1)

        xx_grid, yy_grid = np.meshgrid(x_grid, y_grid)

        if self.m_mask_position == "mean":
            mask = np.ones(im_dim)

            cent_x = int(np.mean(star_position[0]))
            cent_y = int(np.mean(star_position[1]))

            rr_grid = np.sqrt((xx_grid - cent_x)**2 + (yy_grid - cent_y)**2)

            mask[rr_grid < mask_radius] = 0.

        elif self.m_mask_position == "exact":
            mask = np.ones((num_frames, im_dim[0], im_dim[1]))

            cent_x = star_position[:, 0]
            cent_y = star_position[:, 1]

            for i in range(num_frames):
                rr_grid = np.sqrt((xx_grid - cent_x[i])**2 + (yy_grid - cent_y[i])**2)
                mask[i, ][rr_grid < mask_radius] = 0.

        return mask

    def _create_basis(self, im_arr):
        """
        Method for creating a set of principle components for a stack of images.
        """

        _, _, V = svds(im_arr.reshape(im_arr.shape[0],
                                      im_arr.shape[1]*im_arr.shape[2]),
                       k=self.m_pca_number)

        # V = V[::-1,]

        pca_basis = V.reshape(V.shape[0],
                              im_arr.shape[1],
                              im_arr.shape[2])

        return pca_basis

    def _model_background(self, basis, im_arr, mask):
        """
        Method for creating a model of the background.
        """

        def _dot_product(x, *p):
            return np.dot(p, x)

        fit_im_chi = np.zeros(im_arr.shape)
        # fit_coeff_chi = np.zeros((im_arr.shape[0], basis.shape[0]))

        basis_reshaped = basis.reshape(basis.shape[0], -1)

        if self.m_mask_position == "mean":
            basis_reshaped_masked = (basis*mask).reshape(basis.shape[0], -1)

        for i in xrange(im_arr.shape[0]):
            if self.m_mask_position == "exact":
                basis_reshaped_masked = (basis*mask[i]).reshape(basis.shape[0], -1)

            data_to_fit = im_arr[i,]

            init = np.ones(basis_reshaped_masked.shape[0])

            fitted = curve_fit(_dot_product,
                               basis_reshaped_masked,
                               data_to_fit.reshape(-1),
                               init)

            fit_im = np.dot(fitted[0], basis_reshaped)
            fit_im = fit_im.reshape(data_to_fit.shape[0], data_to_fit.shape[1])

            fit_im_chi[i,] = fit_im
            # fit_coeff_chi[i,] = fitted[0]

        return fit_im_chi

    def run(self):
        """
        Run method of the module. Creates a PCA basis set of the background frames, masks the PSF
        in the star frames, fits the star frames with a linear combination of the principle
        components, and writes the background subtracted star frames and the background residuals
        that are subtracted.

        :return: None
        """

        image_memory = self._m_config_port.get_attribute("MEMORY")

        pixscale = self.m_star_in_port.get_attribute("PIXSCALE")

        star_position = self.m_star_in_port.get_attribute("STAR_POSITION")

        self.m_mask_radius /= pixscale

        im_background = self.m_background_in_port.get_all()

        sys.stdout.write("Creating PCA basis set...")
        sys.stdout.flush()
        basis_pca = self._create_basis(im_background)
        sys.stdout.write(" [DONE]\n")
        sys.stdout.flush()

        num_frames = self.m_star_in_port.get_shape()[0]
        num_stacks = int(float(num_frames)/float(image_memory))

        if self.m_mask_position == "mean":
            mask = self._create_mask(self.m_mask_radius, star_position, num_frames)

        for i in range(num_stacks):
            progress(i, num_stacks, "Calculating background model...")

            frame_start = i*image_memory
            frame_end = i*image_memory+image_memory

            im_star = self.m_star_in_port[frame_start:frame_end,]

            if self.m_mask_position == "exact":
                mask = self._create_mask(self.m_mask_radius,
                                         star_position[frame_start:frame_end, :],
                                         frame_end-frame_start)

            im_star_mask = im_star*mask
            fit_im = self._model_background(basis_pca, im_star_mask, mask)

            if i == 0:
                self.m_subtracted_out_port.set_all(im_star-fit_im)
                if self.m_residuals_out_tag is not None:
                    self.m_residuals_out_port.set_all(fit_im)

            else:
                self.m_subtracted_out_port.append(im_star-fit_im)
                if self.m_residuals_out_tag is not None:
                    self.m_residuals_out_port.append(fit_im)

        sys.stdout.write("Calculating background model... [DONE]\n")
        sys.stdout.flush()

        if num_frames%image_memory > 0:
            frame_start = num_stacks*image_memory
            frame_end = num_frames

            im_star = self.m_star_in_port[frame_start:frame_end,]

            mask = self._create_mask(self.m_mask_radius,
                                     star_position[frame_start:frame_end, :],
                                     frame_end-frame_start)

            im_star_mask = im_star*mask
            fit_im = self._model_background(basis_pca, im_star_mask, mask)

            self.m_subtracted_out_port.append(im_star-fit_im)
            if self.m_residuals_out_tag is not None:
                self.m_residuals_out_port.append(fit_im)

        self.m_subtracted_out_port.copy_attributes_from_input_port(self.m_star_in_port)
        self.m_subtracted_out_port.add_history_information("Background",
                                                           "PCA subtraction")

        if self.m_residuals_out_tag is not None:
            self.m_residuals_out_port.copy_attributes_from_input_port(self.m_star_in_port)
            self.m_residuals_out_port.add_history_information("Background",
                                                              "PCA residuals")

        self.m_subtracted_out_port.close_port()


class PCABackgroundDitheringModule(ProcessingModule):
    """
    Module for PCA-based background subtraction of data with dithering. This is a wrapper that
    applies the processing modules required for the PCA background subtraction.
    """

    def __init__(self,
                 center,
                 name_in='pca_dither',
                 image_in_tag="im_arr",
                 image_out_tag="im_pca_bg",
                 shape=(100, 100),
                 cubes_per_position=1,
                 gaussian=0.15,
                 pca_number=60,
                 mask_radius=0.7,
                 **kwargs):
        """
        Constructor of PCABackgroundDitheringModule.

        :param center: Tuple with centers of the dither positions. The format should be similar
                       to ((x0,y0), (x1,y1)) but not restricted to two dither positions. The
                       order of the coordinates should correspond to the order in which the star is
                       present at that specific dither position. So (x0,y0) corresponds with the
                       dither position where the star appears first.
        :type center: tuple, int
        :param name_in: Unique name of the module instance.
        :type name_in: str
        :param image_in_tag: Tag of the database entry that is read as input.
        :type image_in_tag: str
        :param image_out_tag: Tag of the database entry that is written as output.
        :type image_out_tag: str
        :param shape: Tuple (delta_x, delta_y) with the image size that is cropped at the
                      specified dither positions.
        :type shape: tuple, int
        :param cubes_per_position: Number of consecutive cubes per dither position.
        :type cubes_per_position: int
        :param gaussian: Full width at half maximum (arcsec) of the Gaussian kernel that is used
                         to smooth the image before the star is located.
        :type gaussian: float
        :param pca_number: Number of principle components.
        :type pca_number: int
        :param mask_radius: Radius of the mask that is placed at the location of the star (arcsec).
        :type mask_radius: float

        :return: None
        """

        if "bad_pixel_box" in kwargs:
            self.m_bp_box = kwargs["bad_pixel_box"]
        else:
            self.m_bp_box = 9

        if "bad_pixel_sigma" in kwargs:
            self.m_bp_sigma = kwargs["bad_pixel_sigma"]
        else:
            self.m_bp_sigma = 5

        if "bad_pixel_iterate" in kwargs:
            self.m_bp_iterate = kwargs["bad_pixel_iterate"]
        else:
            self.m_bp_iterate = 1

        if "mask_position" in kwargs:
            self.m_mask_pos = kwargs["mask_position"]
        else:
            self.m_mask_pos = "exact"

        super(PCABackgroundDitheringModule, self).__init__(name_in)

        self.m_image_in_port = self.add_input_port(image_in_tag)

        self.m_center = center
        self.m_shape = shape
        self.m_cubes_per_position = cubes_per_position
        self.m_gaussian = gaussian
        self.m_pca_number = pca_number
        self.m_mask_radius = mask_radius

        self.m_image_in_tag = image_in_tag
        self.m_image_out_tag = image_out_tag

    def run(self):
        """
        Run method of the module. Cuts out the detector sections at the different dither positions,
        prepares the PCA background subtraction, applies a bad pixel correction, locates the star
        in each image, runs the PCA background subtraction, combines the output from the different
        dither positions is written to a single database tag.

        :return: None
        """

        n_dither = np.size(self.m_center, 0)
        star_pos = np.arange(0, n_dither, 1)
        tags = []

        for i, position in enumerate(self.m_center):
            print "Processing dither position "+str(i+1)+" out of "+str(n_dither)+"..."

            cut = CutAroundPositionModule(new_shape=self.m_shape,
                                          center_of_cut=position,
                                          name_in="cut"+str(i),
                                          image_in_tag=self.m_image_in_tag,
                                          image_out_tag="dither"+str(i+1))

            cut.connect_database(self._m_data_base)
            cut.run()

            prepare = PCABackgroundPreparationModule(dither=(n_dither,
                                                             self.m_cubes_per_position,
                                                             star_pos[i]),
                                                     name_in="prepare"+str(i),
                                                     image_in_tag="dither"+str(i+1),
                                                     star_out_tag="star"+str(i+1),
                                                     background_out_tag="background"+str(i+1))

            prepare.connect_database(self._m_data_base)
            prepare.run()

            bp_star = BadPixelCleaningSigmaFilterModule(name_in="bp_star"+str(i),
                                                        image_in_tag="star"+str(i+1),
                                                        image_out_tag="star_bp"+str(i+1),
                                                        box=self.m_bp_box,
                                                        sigma=self.m_bp_sigma,
                                                        iterate=self.m_bp_iterate)

            bp_star.connect_database(self._m_data_base)
            bp_star.run()

            bp_bg = BadPixelCleaningSigmaFilterModule(name_in="bp_background"+str(i),
                                                      image_in_tag="background"+str(i+1),
                                                      image_out_tag="background_bp"+str(i+1),
                                                      box=self.m_bp_box,
                                                      sigma=self.m_bp_sigma,
                                                      iterate=self.m_bp_iterate)

            bp_bg.connect_database(self._m_data_base)
            bp_bg.run()

            star = LocateStarModule(name_in="star"+str(i),
                                    data_tag="star_bp"+str(i+1),
                                    gaussian_fwhm=self.m_gaussian)

            star.connect_database(self._m_data_base)
            star.run()

            pca = PCABackgroundSubtractionModule(pca_number=self.m_pca_number,
                                                 mask_radius=self.m_mask_radius,
                                                 mask_position=self.m_mask_pos,
                                                 name_in="pca_background"+str(i),
                                                 star_in_tag="star_bp"+str(i+1),
                                                 background_in_tag="background_bp"+str(i+1),
                                                 subtracted_out_tag="pca_bg_sub"+str(i+1),
                                                 residuals_out_tag=None)

            pca.connect_database(self._m_data_base)
            pca.run()

            tags.append("pca_bg_sub"+str(i+1))

        combine = CombineTagsModule(name_in="combine",
                                    image_in_tags=tags,
                                    image_out_tag=self.m_image_out_tag)

        combine.connect_database(self._m_data_base)
        combine.run()


class PCABackgroundNoddingModule(ProcessingModule):
    """
    Module for PCA-based background subtraction of data with nodding (e.g., NACO AGPM data). This
    is a wrapper that applies the processing modules required for the PCA background subtraction.
    """

    def __init__(self,
                 name_in='pca_dither',
                 star_in_tag="im_star",
                 background_in_tag="im_background",
                 image_out_tag="im_pca_bg",
                 gaussian=0.15,
                 pca_number=60,
                 mask_radius=0.7,
                 **kwargs):
        """
        Constructor of PCABackgroundNoddingModule.

        :param name_in: Unique name of the module instance.
        :type name_in: str
        :param star_in_tag: Tag of the database entry with the images containing the star that are
                            read as input.
        :type star_in_tag: str
        :param background_in_tag: Tag of the database with the images containing the background
                                  that are read as input.
        :type background_in_tag: str
        :param image_out_tag: Tag of the database entry that is written as output.
        :type image_out_tag: str
        :param gaussian: Full width at half maximum (arcsec) of the Gaussian kernel that is used
                         to smooth the image before the star is located.
        :type gaussian: float
        :param pca_number: Number of principle components.
        :type pca_number: int
        :param mask_radius: Radius of the mask that is placed at the location of the star (arcsec).
        :type mask_radius: float

        :return: None
        """

        if "mask_position" in kwargs:
            self.m_mask_pos = kwargs["mask_position"]
        else:
            self.m_mask_pos = "exact"

        super(PCABackgroundNoddingModule, self).__init__(name_in)

        self.m_star_in_port = self.add_input_port(star_in_tag)
        self.m_background_in_port = self.add_input_port(background_in_tag)

        self.m_gaussian = gaussian
        self.m_pca_number = pca_number
        self.m_mask_radius = mask_radius

        self.m_star_in_tag = star_in_tag
        self.m_background_in_tag = background_in_tag
        self.m_image_out_tag = image_out_tag

    def run(self):
        """
        Run method of the module. Locates the star in each image, runs the PCA background
        subtraction, combines the output from the different dither positions is written to
        a single database tag.

        :return: None
        """

        star = LocateStarModule(name_in="star",
                                data_tag=self.m_star_in_tag,
                                gaussian_fwhm=self.m_gaussian)

        star.connect_database(self._m_data_base)
        star.run()

        pca = PCABackgroundSubtractionModule(pca_number=self.m_pca_number,
                                             mask_radius=self.m_mask_radius,
                                             mask_position=self.m_mask_pos,
                                             name_in="pca_background",
                                             star_in_tag=self.m_star_in_tag,
                                             background_in_tag=self.m_background_in_tag,
                                             subtracted_out_tag=self.m_image_out_tag,
                                             residuals_out_tag=None)

        pca.connect_database(self._m_data_base)
        pca.run()


class NoddingBackgroundModule(ProcessingModule):
    """
    Module for background subtraction of data obtained with nodding (e.g., NACO AGPM data).
    """

    def __init__(self,
                 name_in="sky_subtraction",
                 sky_in_tag="sky_arr",
                 science_in_tag="im_arr",
                 image_out_tag="im_arr",
                 mode="both"):
        """
        Constructor of NoddingBackgroundModule.

        :param name_in: Unique name of the module instance.
        :type name_in: str
        :param sky_in_tag: Tag of the database entry with sky frames that are read as input.
        :type sky_in_tag: str
        :param science_data_in_tag: Tag of the database entry with science frames that are read as
                                    input.
        :type science_data_in_tag: str
        :param image_out_tag: Tag of the database entry with sky subtracted images that are written
                              as output.
        :type image_out_tag: str

        :return: None
        """

        super(NoddingBackgroundModule, self).__init__(name_in=name_in)

        self.m_sky_in_port = self.add_input_port(sky_in_tag)
        self.m_science_in_port = self.add_input_port(science_in_tag)
        self.m_image_out_port = self.add_output_port(image_out_tag)

        self.m_time_stamps = []

        if mode in ["next", "previous", "both"]:
            self.m_mode = mode
        else:
            raise ValueError("Mode needs to be next, previous or both.")

    def _create_time_stamp_list(self):
        """
        Internal method for assigning a time stamp, based on the exposure number ID, to each cube
        of sky and science frames.
        """

        class TimeStamp:
            def __init__(self,
                         time,
                         sky_or_science,
                         index):
                self.m_time = time
                self.m_sky_or_science = sky_or_science
                self.m_index = index

            def __repr__(self):
                return repr((self.m_time,
                             self.m_sky_or_science,
                             self.m_index))

        exp_no = self.m_sky_in_port.get_attribute("EXP_NO")

        for i, item in enumerate(exp_no):
            self.m_time_stamps.append(TimeStamp(item,
                                                "SKY",
                                                i))

        exp_no = self.m_science_in_port.get_attribute("EXP_NO")
        nframes = self.m_science_in_port.get_attribute("NFRAMES")

        current = 0
        for i, item in enumerate(exp_no):
            self.m_time_stamps.append(TimeStamp(item,
                                                "SCIENCE",
                                                slice(current, current+nframes[i])))
            current += nframes[i]

        self.m_time_stamps = sorted(self.m_time_stamps, key=lambda time_stamp: time_stamp.m_time)

    def calc_sky_frame(self,
                       index_of_science_data):
        """
        Method for finding the required sky frame (next, previous, or the mean of next and
        previous) by comparing the time stamp of the science frame with preceding and following
        sky frames.
        """

        # check if there is at least one SKY in the database
        if not any(x.m_sky_or_science == "SKY" for x in self.m_time_stamps):
            raise ValueError('List of time stamps does not contain any SKY frames')

        def search_for_next_sky():
            for i in range(index_of_science_data, len(self.m_time_stamps)):
                if self.m_time_stamps[i].m_sky_or_science == "SKY":
                    return self.m_sky_in_port[self.m_time_stamps[i].m_index, :, :]

            # no next sky found look for previous sky
            return search_for_previous_sky()

        def search_for_previous_sky():
            for i in reversed(range(0, index_of_science_data)):
                if self.m_time_stamps[i].m_sky_or_science == "SKY":
                    return self.m_sky_in_port[self.m_time_stamps[i].m_index, :, :]

            # no previous sky found look for next sky
            return search_for_next_sky()

        if self.m_mode == "next":
            return search_for_next_sky()

        if self.m_mode == "previous":
            return search_for_previous_sky()

        if self.m_mode == "both":
            previous_sky = search_for_previous_sky()
            next_sky = search_for_next_sky()
            return (previous_sky + next_sky)/2.0

    def run(self):
        """
        Run method of the module. Create list of time stamps, get sky and science frames, and
        subtract the sky background from the science frames.

        :return: None
        """

        self._create_time_stamp_list()

        self.m_image_out_port.del_all_data()
        self.m_image_out_port.del_all_attributes()

        for i, time_entry in enumerate(self.m_time_stamps):
            progress(i, len(self.m_time_stamps), "Running NoddingBackgroundModule...")

            if time_entry.m_sky_or_science == "SKY":
                continue

            sky = self.calc_sky_frame(i)

            science = self.m_science_in_port[time_entry.m_index, ]

            self.m_image_out_port.append(science - sky[None, ],
                                         data_dim=3)

        sys.stdout.write("Running NoddingBackgroundModule... [DONE]\n")
        sys.stdout.flush()

        self.m_image_out_port.copy_attributes_from_input_port(self.m_science_in_port)

        self.m_image_out_port.add_history_information("Background",
                                                      "Nodding sky subtraction")

        self.m_image_out_port.close_port()
