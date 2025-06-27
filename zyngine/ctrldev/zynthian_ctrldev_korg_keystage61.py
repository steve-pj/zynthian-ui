#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Control Device Driver
#
# Zynthian Control Device Driver for "Korg keystage"
#
# Copyright (C) 2024 Fernando Moyano <jofemodo@zynthian.org>
#
# ******************************************************************************
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the LICENSE.txt file.
#
# ******************************************************************************

import logging
from time import sleep
from math import log10

# Zynthian specific modules
from zyncoder.zyncore import lib_zyncore
from zyngine.zynthian_signal_manager import zynsigman
from zyngine.ctrldev.zynthian_ctrldev_base import zynthian_ctrldev_zynmixer
#from zyngine.ctrldev.zynthian_ctrldev_base_extended import KnobSpeedControl
#from zyngui.zynthian_gui_control import zynthian_gui_control
#from zyngui import zynthian_gui
#from zyngui import zynthian_gui_base
#from zyngui import zynthian_gui_config
#import zyngui
#import zyngui.zynthian_gui_control
#import zyngui.zynthian_gui_selector

# --------------------------------------------------------------------------#
# Korg Keystage Integration                                                 #
# --------------------------------------------------------------------------#

# Current functionality - but with bugs
# Driver based on Korg NanoKontrol2 Driver with extra code taken from Akai and Mackie Drivers
# Keystage Driver starts in Native Mode which allows text to be sent to Main Display and Knob Displays via sysex
# In Native mode all Knob CCnums are fixed (0 -7)
# Exit button disables/enables Native mode, all CCs can be selected, but display cannot be controlled (I think! need to check this)
# Tranport should work as per NanoKontrol2 driver (ie cycle button activates shift)
# There are 8 'Modes' selectable by the big knob (this is the only encoder), Chain, Volume, Pan, Mute, Solo, Active Chain, ZynthianUI and Device.
# Mode is displayed on top right of Main Display
# Chain displays parameters for the first channel ie Chain Name, Volume, Pan, Mute, Solo, Active.

# Volume, Pan, Mute, Solo, Active display the values for each mixer channel (if audio)
# The knobs change the value on Zynthian and the Keystage, but values are not always retained on KS display - Review this as it might be working now

# Device swaps to device mode. Knobs call ZYNPOT CUIA but as they're rotary pots rather than encoders work using 'pick-up mode' - Mostly works, but could do with improving especially at extremes
# Zyncoder parameters or values are not displayed on Keystage in ZynthianUI mode - Not sure how useful this is - does appear to change on screen values if a chain is selected without triggering 'Device mode'

# TODO Display Current Snapshot on center of Main display - may decide to change this later though
# TODO Fix mode selection - Looks like the may be a better way of doing this loking at other driver code.
# TODO Get Chain Mode to actually do something. Needs to display 'Active Chain' not first and paramerts to be changed via appropriate knob. - ACTIVE CHAIN DISPLAY Working exept for arm
# TODO Fix retention of vol, pan, etc values in mixer and chain modes - working except for select but Chain mode not and broken again. - Chain Mode currently not borked as much
# TODO Device mode - can rotary pots be used in place of encoders? If we can get the current value might be able to work out some maths as a fudge? FIXED - Mostly working in pickup mode now.
# TODO Get device parameter names ie Resonance, Cutoff, etc. Close to working, but code needs cleaning and theres some corruption of the display- whats causing this, is it drive code or sysex implementation
# TODO Does this come from a JALV file, how do we know which 4 paramerts are active, avoid using midi learn if possible. Intially working but up down button to select groups isnt always working properly on KEYSTAGE but is on GUI - fudged a fix using a short sleep before updating the display.
# TODO If we can get the above completed clean up the CODE!!! before progressing further!

class zynthian_ctrldev_korg_keystage61(zynthian_ctrldev_zynmixer):

    dev_ids = ["Keystage IN 1"]

    #dev_ids = ["*"]
    driver_name = "Korg Keystage61"
    driver_description = "Korg Keystage61 with zynmixer, transport and chains"

    midi_chan = 0x0
    sysex_answer_cb = None

    rec_mode = 0
    shift = False
    _is_shifted = shift
    native_mode = False
    display_text = "CC"
    unroute_from_chains = False
    
    # The following are from the nanoKontrol
    cycle_ccnum = 46
    track_left_ccnum = 58
    track_right_ccnum = 59
    marker_set_ccnum = 60
    marker_left_ccnum = 61
    marker_right_ccnum = 62
    transport_frwd_ccnum = 43
    transport_ffwd_ccnum = 44
    transport_stop_ccnum = 42
    transport_play_ccnum = 41
    transport_rec_ccnum = 45

    solo_ccnums = [32, 33, 34, 35, 36, 37, 38, 39]
    mute_ccnums = [48, 49, 50, 51, 52, 53, 54, 55]
    rec_ccnums = [64, 65, 66, 67, 68, 69, 70, 71]
    knobs_ccnum = [16, 17, 18, 19, 20, 21, 22, 23]
    faders_ccnum = [0, 1, 2, 3, 4, 5, 6, 7]
    # End of nanokontrol ccnums
    
    # Native Mode ccs
    native_knobs_ccnum = [0, 1, 2, 3, 4, 5, 6, 7]
    native_transport_play_ccnum = 41
    native_transport_stop_ccnum = 42
    native_transport_frwd_ccnum = 43
    native_transport_ffwd_ccnum = 44
    native_transport_rec_ccnum = 45
    native_cycle_ccnum = 46
    native_tempo_ccnum = 47
    native_metro_ccnum = 48
    native_undo_ccnum = 49
    native_val_down_ccnum = 60
    native_val_up_ccnum = 61
    native_next_track_ccnum = 58
    native_previous_track_ccnum = 59
    native_value_knob_left_ccnum = 62
    native_value_knob_right_ccnum = 63
    native_exit_ccnum = 120
    #This creates a list of ccvals to be used later, hopefully o emulate enocoders ;-)
    ccvals = []
    ccvals_full = []
    ccvals_ctrl_res = []

    #ALIAS for KNOBS
    KNOB_1 = KNOB_LAYER = 0x00
    KNOB_2 = KNOB_SNAPSHOT = 0x01
    KNOB_3 = 0x02
    KNOB_4 = 0x03
    KNOB_5 = KNOB_BACK = 0x04
    KNOB_6 = KNOB_SELECT = 0x05
    KNOB_7 = 0x06
    KNOB_8 = 0x07

    # PC numbers for related actions
    program = 0
    PROG_MIXER_MODE = 4
    PROG_DEVICE_MODE = 5
    PROG_PATTERN_MODE = 6
    PROG_NOTEPAD_MODE = 7
    PROG_USER_MODE = 8
    PROG_CONFIG_MODE = 9

    PROG_OPEN_MIXER = 0
    PROG_OPEN_ZYNPAD = 1
    PROG_OPEN_TEMPO = 2
    PROG_OPEN_SNAPSHOT = 3

    # Function/State constants
    func = 0
    FN_VOLUME = 1
    FN_PAN = 2
    FN_SOLO = 3
    FN_MUTE = 4
    FN_SELECT = 5

    # for encoder emulation - remove if not used
    #_knobs_ease = KnobSpeedControl()
    

    # Initial control modes - delete if setup elsewhere
    func = 0
    control_mode = 'Chain'

    # Control Modes - not used at the moment bu may re-implement
    #control_mode = ['Chain','Volume', 'Pan', 'Solo', 'Mute', 'Select', Device]

    # Function to initialise class
    def __init__(self, state_manager, idev_in, idev_out=None):
        self.midimix_bank = 0
        super().__init__(state_manager, idev_in, idev_out)

    #Borrowed from Mackie driver
    def _on_gui_show_screen(self, **kwargs):
        logging.debug(f'KEYSTAGE DRIVER : got screen change: {kwargs}')
        if 'screen' in kwargs.keys():
            self.gui_screen = kwargs['screen']
        self.refresh()  # I'm using the screen change signal to refresh all channels particularly at the beginning

    def _on_gui_control_mode(self, **kwargs):
        logging.debug(f'KEYSTAGE DRIVER : ON GUI CONTROL MODE : {kwargs}')
        if 'screen' in kwargs.keys():
            self.gui_screen = kwargs['screen']
        self.refresh()

    def send_sysex(self, data):
        if self.idev_out is not None:
            msg = bytes.fromhex(
                f"F0 42 4{hex(self.midi_chan)[2:]} 00 01 69 09 {data} F7")
            lib_zyncore.dev_send_midi_event(self.idev_out, msg, len(msg))
            #logging.debug(f"Sysex Message Sent : {msg}, Length : {len(msg)}")

    def korg_sysex_midi2data(self, midi):
        data = bytearray()
        pos = 0
        while True:
            bitsbyte = midi[pos]
            for i in range(0, 7):
                b7 = (bitsbyte >> i) & 0x1
                byte = midi[pos + 1 + i] | (b7 << 7)
                data.append(byte)
            pos += 8
            if pos > len(midi) - 7:
                break
        while len(data) < 339:
            data.append(0)
        return data

    def korg_sysex_data2midi(self, data):
        midi = bytearray()
        pos = 0
        while True:
            bitsbyte = 0x0
            for i in range(0, 7):
                bitsbyte |= (data[pos + i] >> 7) << i
            midi.append(bitsbyte)
            for i in range(0, 7):
                midi.append(data[pos + i] & 0x7F)
            pos += 7
            if pos > len(data) - 6:
                break
        while len(midi) < 388:
            midi.append(0)
        return midi
    
    def korg_keystage_display_data(self, *text):
        if len(text) > 11:
            text_len = 12
        else:
            text_len = len(text)    
        self.display_text = ('{: ^12}'.format(text[:text_len]))
        korg_func_1 = 3 + len(self.display_text)
        korg_func_2 = str(korg_func_1).zfill(2)
        dsp_txt_hex_lst=[]
        for i in self.display_text:
            temp=ord(i)
            temp=hex(temp)
            temp=temp[2:4]
            dsp_txt_hex_lst.append(temp)
        delimiter = " "
        dsp_txt_hex = delimiter.join(dsp_txt_hex_lst)
        self.send_sysex(str(korg_func_2) + " " + "00 00 28 01 01 " + str(dsp_txt_hex))

    def korg_keystage_display_data2(self, column, row, text):
        self.column = str(column).zfill(2)
        self.row = str(row).zfill(2)
        if len(text) > 11:
            text_len = 12
        else:
            text_len = len(text) 
        self.display_text = ('{: ^12}'.format(text[:text_len]))
        korg_func_1 = 3 + len(self.display_text)
        korg_func_2 = str(korg_func_1).zfill(2)
        dsp_txt_hex_lst=[]
        for i in self.display_text:
            temp=ord(i)
            temp=hex(temp)
            temp=temp[2:4]
            dsp_txt_hex_lst.append(temp)
        delimiter = " "
        dsp_txt_hex = delimiter.join(dsp_txt_hex_lst)
        self.send_sysex(str(korg_func_2) + " " + "00 00 28 " + str(self.column) + " " + str(self.row) + " " + str(dsp_txt_hex))   

    def update_bottom_knob_value(self, channel, bottom_text):
        self.channel = str(channel + 1).zfill(2)
        if len(bottom_text) > 11:
            text_len = 12
        else:
            text_len = len(bottom_text)  
        self.display_text = ('{:^12}'.format(bottom_text[:text_len]))
        korg_func_1 = 3 + len(self.display_text)
        korg_func_2 = str(korg_func_1).zfill(2)
        dsp_txt_hex_lst=[]
        for i in self.display_text:
            temp=ord(i)
            temp=hex(temp)
            temp=temp[2:4]
            dsp_txt_hex_lst.append(temp)
        delimiter = " "
        dsp_txt_hex = delimiter.join(dsp_txt_hex_lst)
        self.send_sysex(str(korg_func_2) + " " + "00 00 28 " + str(self.channel) + " 01 " + str(dsp_txt_hex))

    def set_mode_native(self):
        # Put Keystage into Native Mode
        self.send_sysex("02 00 00 00 01")
        self.native_mode = True
        # Logging Info
        logging.debug(f'KEYSTAGE DRIVER : Native Mode enabled')
   
    def set_mode_normal(self):
        # Disable Native mode and put Keystage into custom mode
        self.send_sysex("02 00 00 00 00")
        self.native_mode = False
        # Logging Info
        logging.debug(f'KEYSTAGE DRIVER : Native Mode disabled')

    #This is for the NanoKontrol2 - Don't think its required or needs to be adapted for Keystage at this point 
    # def set_mode_led_external(self):
    #     # Send Scene Data Dump Request
    #     self.sysex_answer_cb = self.cb_set_mode_led_external
    #     self.send_sysex("1F 10 00")
    
    #As Above
    # def cb_set_mode_led_external(self, sysex_answer):
    #     self.sysex_answer_cb = None
    #     # Toggle led mode in Scene data
    #     scene_data = self.korg_sysex_midi2data(sysex_answer[13:-1])
    #     scene_data[2] = 0x1
    #     logging.debug(f"SCENE DATA MODIFIED: {scene_data.hex(' ')}")
    #     # Send back modified scene data
    #     midi_data = self.korg_sysex_data2midi(scene_data)
    #     self.sysex_answer_cb = self.cb_sysex_ack
    #     self.send_sysex(f"7F 7F 02 03 05 40 {midi_data.hex(' ')}")

    #Ditto
    # def cb_sysex_ack(self, sysex_answer):
    #     self.sysex_answer_cb = None
    #     if sysex_answer[8] == 0x23:
    #         logging.debug("Received SysEx ACK. Data Load operation success.")
    #     elif sysex_answer[8] == 0x24:
    #         logging.error("Received SysEx NAK. Data Load operation failed.")
    #     else:
    #         logging.error(f"Unknown SysEx response => {sysex_answer.hex(' ')}")

    def init(self):
        # Enable LED control - Not needed for Keystage
        #self.set_mode_led_external()
        # Enable Native mode
        logging.debug(f'KEYSTAGE61 DRIVER : Enabling Native Mode')
        self.set_mode_native()
        # Set Initial Control Mode
        self.func = 0
        self.control_mode = 'Chain'
        try:
            self.control_mode_handler(self.func)
        except:
            logging.debug(f' KEYSTAGE DRIVER : Failed to start Control Mode Handler')
        self.display_text = self.control_mode
        chain_name = ' '
        # Set Intial Display (just knobs)
        logging.debug(f'KEYSTAGE61 DRIVER : Initialising knob display')
        self.initialise_chain()
        logging.debug(f'KEYSTAGE61 DRIVER : Initialising chain names') 
        # Register signals
        zynsigman.register_queued(
            zynsigman.S_GUI, zynsigman.SS_GUI_SHOW_SCREEN, self._on_gui_show_screen)
        zynsigman.register_queued(
            zynsigman.S_AUDIO_PLAYER, self.state_manager.SS_AUDIO_PLAYER_STATE, self.refresh_audio_transport)
        zynsigman.register_queued(
            zynsigman.S_AUDIO_RECORDER, self.state_manager.SS_AUDIO_RECORDER_STATE, self.refresh_audio_transport)
        zynsigman.register_queued(
            zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_PLAYER_STATE, self.refresh_midi_transport)
        zynsigman.register_queued(
            zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_RECORDER_STATE, self.refresh_midi_transport)
        zynsigman.register_queued(
            zynsigman.S_CHAIN_MAN, self.chain_manager.SS_SET_ACTIVE_CHAIN, self.update_mixer_active_chain)
        zynsigman.register_queued(
            zynsigman.S_CHAIN_MAN, self.chain_manager.SS_MOVE_CHAIN, self.refresh)
        zynsigman.register_queued(
            zynsigman.S_AUDIO_MIXER, self.zynmixer.SS_ZCTRL_SET_VALUE, self.update_mixer_strip)
        super().init()

    def end(self):
        super().end()
        # Unregister signals
        zynsigman.unregister(zynsigman.S_GUI, zynsigman.SS_GUI_SHOW_SCREEN, self._on_gui_show_screen)
        zynsigman.unregister(zynsigman.S_AUDIO_PLAYER,
            self.state_manager.SS_AUDIO_PLAYER_STATE, self.refresh_audio_transport)
        zynsigman.unregister(zynsigman.S_AUDIO_RECORDER,
            self.state_manager.SS_AUDIO_RECORDER_STATE, self.refresh_audio_transport)
        zynsigman.unregister(
            zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_PLAYER_STATE, self.refresh_midi_transport)
        zynsigman.unregister(
            zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_RECORDER_STATE, self.refresh_midi_transport)
        zynsigman.unregister(
            zynsigman.S_CHAIN_MAN, self.chain_manager.SS_SET_ACTIVE_CHAIN, self.update_mixer_active_chain)
        zynsigman.unregister(zynsigman.S_CHAIN_MAN,
            self.chain_manager.SS_MOVE_CHAIN, self.refresh)
        zynsigman.unregister(
            zynsigman.S_AUDIO_MIXER, self.zynmixer.SS_ZCTRL_SET_VALUE, self.update_mixer_strip)
        self.light_off()

    def refresh_audio_transport(self, **kwargs):
        if self.shift:
            return
        # REC Button
        if self.state_manager.audio_recorder.rec_proc:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_rec_ccnum, 0x7F)
        else:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_rec_ccnum, 0)
        # STOP button
        lib_zyncore.dev_send_ccontrol_change(
            self.idev_out, self.midi_chan, self.native_transport_stop_ccnum, 0)
        # PLAY button:
        if self.state_manager.status_audio_player:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_play_ccnum, 0x7F)
        else:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_play_ccnum, 0)

    def refresh_midi_transport(self, **kwargs):
        if not self.shift:
            return
        # REC Button
        if self.state_manager.status_midi_recorder:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_rec_ccnum, 0x7F)
        else:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_rec_ccnum, 0)
        # STOP button
        lib_zyncore.dev_send_ccontrol_change(
            self.idev_out, self.midi_chan, self.native_transport_stop_ccnum, 0)
        # PLAY button:
        if self.state_manager.status_midi_player:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_play_ccnum, 0x7F)
        else:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_play_ccnum, 0)

    # This is for Korg NanoControl - Not sure if required or should be adapted for KEYSTAGE as it doesnt have LEDS
    # Update LED status for a single strip
    def update_mixer_strip(self, chan, symbol, value):
        if self.idev_out is None:
            return
        chain_id = self.chain_manager.get_chain_id_by_mixer_chan(chan)
        if chain_id:
            col = self.chain_manager.get_chain_index(chain_id)
            if self.midimix_bank:
                col -= 8
            if 0 <= col < 8:
                if symbol == "mute":
                    lib_zyncore.dev_send_ccontrol_change(
                        self.idev_out, self.midi_chan, self.mute_ccnums[col], value * 0x7F)
                elif symbol == "solo":
                    lib_zyncore.dev_send_ccontrol_change(
                        self.idev_out, self.midi_chan, self.solo_ccnums[col], value * 0x7F)
                elif symbol == "rec" and self.rec_mode:
                    lib_zyncore.dev_send_ccontrol_change(
                        self.idev_out, self.midi_chan, self.rec_ccnums[col], value * 0x7F)

    # This is for Korg NanoControl - Not sure if required or should be adapted for KEYSTAGE as it doesnt have LEDS
    # Update LED status for active chain
    def update_mixer_active_chain(self, active_chain):
        if self.rec_mode:
            return
        if self.midimix_bank:
            col0 = 8
        else:
            col0 = 0
        for i in range(0, 8):
            chain_id = self.chain_manager.get_chain_id_by_index(col0 + i)
            if chain_id and chain_id == active_chain:
                rec = 0x7F
            else:
                rec = 0
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.rec_ccnums[i], rec)
            #logging.debug(f'KEYSTAGE DEBUGGER - Active Chain is : {active_chain}')

    # Update full LED status
    def refresh(self):
        if self.idev_out is None:
            return

        # This is for Korg NanoControl - Not sure if required or should be adapted for KEYSTAGE as it doesnt have LEDS
        # Bank selection LED
        if self.midimix_bank:
            col0 = 8
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_frwd_ccnum, 0)
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_ffwd_ccnum, 0x7F)
        else:
            col0 = 0
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_frwd_ccnum, 0x7F)
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_transport_ffwd_ccnum, 0)

        if self.shift:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_cycle_ccnum, 0x7F)
            logging.debug(f'KEYSTAGE DRIVER {self.idev_out}, {self.midi_chan}, {self.native_cycle_ccnum}')
            self.refresh_midi_transport()
        else:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.native_cycle_ccnum, 0)
            self.refresh_audio_transport()

        # This is for Korg NanoControl - Not sure if required or should be adapted for KEYSTAGE as it doesnt have LEDS
        # Strips Leds
        for i in range(0, 8):
            chain = self.chain_manager.get_chain_by_index(col0 + i)

            if chain and chain.mixer_chan is not None:
                mute = self.zynmixer.get_mute(chain.mixer_chan) * 0x7F
                solo = self.zynmixer.get_solo(chain.mixer_chan) * 0x7F
            else:
                chain = None
                mute = 0
                solo = 0

            if not self.rec_mode:
                if chain and chain == self.chain_manager.get_active_chain():
                    rec = 0x7F
                else:
                    rec = 0
            else:
                if chain and chain.mixer_chan is not None:
                    rec = self.state_manager.audio_recorder.is_armed(
                        chain.mixer_chan) * 0x7F
                else:
                    rec = 0

            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.mute_ccnums[i], mute)
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.solo_ccnums[i], solo)
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, self.rec_ccnums[i], rec)
        
        # Chain IDs for Keystage - disabled for now as its overwriting chain mode top knob display
        #self.chain_name_handler()
        #self.device_mode_handler()
        #self.init2()

    def get_mixer_chan_from_device_col(self, col):
        if self.midimix_bank:
            col += 8
        chain = self.chain_manager.get_chain_by_index(col)
        if chain:
            return chain.mixer_chan
        else:
            return None
        
    # not sure if this is working yet - alt function
    def get_ordered_chain_ids_test(self):
        chain_ids = list(self.chain_manager.ordered_chain_ids)
        ordered_chain_ids_test = []
        for chain_id in chain_ids:
            chain = self.chain_manager.chains[chain_id]
            ordered_chain_ids_test.append(chain_id)
        return ordered_chain_ids_test
    
    def get_chain_by_position(self, pos):
        ordered_chain_ids_test = self.get_ordered_chain_ids_test()
        if pos < len(ordered_chain_ids_test):
            return self.chain_manager.chains[ordered_chain_ids_test[pos]]
        else:
            return None
        
    #This sets all the knob displays to blanks ' ' then displays active chain
    def initialise_chain(self):
        for i in range(0, 8):
            text = '            '
            self.korg_keystage_display_data2(self.native_knobs_ccnum[i]+1,0,text)
            self.korg_keystage_display_data2(self.native_knobs_ccnum[i]+1,1,text)
        if self.midimix_bank:
            col0 = 8
        else:
            col0 = 0
        for i in range(0, 8):
            chain_name = ' '
            try:
                chain = self.get_chain_by_position(col0 + i)
            except:
                chain = self.get_chain_by_position(0)
                logging.debug(f'KEYSTAGE DRIVER : USING CHAIN 0)')
            if chain is not None:
                chain_name = str(chain.get_title())
            self.korg_keystage_display_data2(self.native_knobs_ccnum[1],0,"Active Chain")   
            self.korg_keystage_display_data2(self.native_knobs_ccnum[i]+1,1,chain_name)
            logging.debug(f' KEYSTAGE DRIVER : Entering Chain Mode ')
            #self.chain_mode_display()
    
    #Gets and displays all parameters for active chain
    def chain_mode_display(self):
        self.control_mode = "Chain"
        self.korg_keystage_display_data2(0,0,self.control_mode)
        bottom_texts = []
        active_chain2 = self.chain_manager.get_active_chain()
        logging.debug(f'KEYSTAGE DRIVER : GETTING ACTIVE CHAIN : {active_chain2}')
        active_chain_id = self.chain_manager.active_chain_id
        logging.debug(f'KEYSTAGE DRIVER : GETTING ACTIVE CHAIN ID : {active_chain_id}')
        try:    
            active_chain_name = str(active_chain2.get_title())
        except:
            active_chain2 = self.get_chain_by_position(0)
            active_chain_name = str(active_chain2.get_title())
            logging.debug(f' KEYSTAGE DRIVER : CANT GET ACTIVE CHAIN TITLE, USING CHAIN 0 INSTEAD')
            #logging.debug(f'active_chain2 is : {active_chain2}')
        active_chain_index = self.chain_manager.get_chain_index(active_chain_id)        
        mixer_chan = self.get_mixer_chan_from_device_col(active_chain_index)
        ## logging.debug(f'KEYSTAGE DRIVER : GET STATE {self.state_manager.get_state()}')
        logging.debug(f'KEYSTAGE DRIVER : Active Chain is {active_chain2} with name {active_chain_name}, id {active_chain_id}, index : {active_chain_index} and mixer channel : {mixer_chan}')
        j = mixer_chan
        for i in range(0, 8):
        #Gets level
            level_value = self.zynmixer.get_level(j)
            if level_value is not None:
                if level_value == 0:
                    level_db = f'infinity dB'
                else:
                    level_db = f'{round(20 * log10(level_value),2)}dB'
                bottom_text = str(level_db)
                top_texts = ["Active Chain", "Volume", "Pan", "Solo", "Mute", "Arm"," ", " "]
                bottom_texts.append(bottom_text)
        #Gets balance
            balance_value = self.zynmixer.get_balance(j)
            if balance_value is not None:
                if balance_value == 0:
                    bottom_text = "<C>"
                else:
                    bottom_text = f'{round(balance_value * 100, 0)}%'
                bottom_texts.append(bottom_text)
        #Gets Solo
            if self.zynmixer.get_solo(j):
                solo_value = 'On'
            else:
                solo_value = ' '
            bottom_text = f'{solo_value}'
            bottom_texts.append(bottom_text)
        #Gets Mute
            if self.zynmixer.get_mute(j):
                mute_value = 'On'
            else:
                mute_value = ' '
            bottom_text = f'{mute_value}'
            bottom_texts.append(bottom_text)
        #Gets Selected (dummy)
            bottom_text = ' '
            bottom_texts.append(bottom_text)
            bottom_texts.append(bottom_text)
            bottom_texts.append(bottom_text)
        #Gets Chain Name
            if self.midimix_bank:
                col0 = 8
            else:
                col0 = 0
            #chainy = self.get_chain_by_position(j)
            #chain_id_str = str(self.chain_manager.get_chain_id_by_index(col0 + j - 1))
            #chain_id = self.chain_manager.get_chain_id_by_index(col0 + j - 1)
            #chain_name = str(chainy.get_title())
            #logging.debug(f'Chain is : {chainy} with name : {chain_name}')
            #self.korg_keystage_display_data2(1,0,chain_name)
            self.korg_keystage_display_data2(i+1,0,top_texts[i])
            self.korg_keystage_display_data2(1,1,active_chain_name)
            self.update_bottom_knob_value(i+1, bottom_texts[i])
        #self.korg_keystage_display_data2(0,0,self.control_mode)
        #self.chain_name_handler()

    # This shouldn't duplicate the midi event processor, but does need to update the displays for each mode when selected.             
    def control_mode_handler(self, func):
        num_of_chains = len(self.chain_manager.chains)
        self.func = func
        text = ' '
        for k in range(0, 8):
            self.korg_keystage_display_data2(k+1,0,text)
            self.korg_keystage_display_data2(k+1,1,text)
        #logging.debug(f'KEYSTAGE DRIVER : function mode: func:{func}')
        if self.func < 7:
            self.chain_name_handler()
            self.state_manager.send_cuia("SCREEN_AUDIO_MIXER")
            if self.func == 0:
                self.control_mode = "Chain"
                self.chain_mode_display()
            elif self.func == 1:
                self.control_mode = "Volume"
                #logging.debug(f'KEYSTAGE DRIVER : Number of Channels : {num_of_chains}')
                for i in range(0, num_of_chains):    
                    self.bottom_text = ' '
                    mixer_chan = self.get_mixer_chan_from_device_col(i)
                    self.level_value = self.zynmixer.get_level(mixer_chan)
                    #logging.debug(f'KEYSTAGE DRIVER : Level Value Channel {i} : {self.zynmixer.get_level(mixer_chan)}')
                    if self.level_value is not None:
                        if self.level_value == 0:
                            self.level_db = f'-infinity dB'
                        else:
                            self.level_db = f'{round(20 * log10(self.level_value),2)}dB'
                            self.bottom_text = str(self.level_db)
                        self.update_bottom_knob_value(i, self.bottom_text)
            elif self.func == 2:
                self.control_mode = "Pan"
                for i in range(0, num_of_chains):
                    self.bottom_text = ' '
                    mixer_chan = self.get_mixer_chan_from_device_col(i)
                    self.balance_value = self.zynmixer.get_balance(mixer_chan)
                    #logging.debug(f'KEYSTAGE DRIVER : Balance Value: Channel {i} : {self.zynmixer.get_balance(mixer_chan)}')
                    if self.balance_value is not None:
                        if self.balance_value == 0:
                            self.bottom_text = '<C>'
                        else:
                            self.bottom_text = f'{round(self.balance_value * 100, 0)}%'
                        self.update_bottom_knob_value(i, self.bottom_text)            
            elif self.func == 3:
                self.control_mode = "Solo"
                for i in range(0, num_of_chains):
                    mixer_chan = self.get_mixer_chan_from_device_col(i)
                    if self.zynmixer.get_solo(mixer_chan):
                        solo_value = 'Solo'
                    else:
                        solo_value = ' '
                    bottom_text = f'{solo_value}'
                    self.update_bottom_knob_value(i, bottom_text)           
            elif self.func == 4:
                self.control_mode = "Mute"
                for i in range(0, num_of_chains):
                    mixer_chan = self.get_mixer_chan_from_device_col(i)
                    if self.zynmixer.get_mute(mixer_chan):
                        mute_value = 'Mute'
                    else:
                        mute_value = ' '
                    bottom_text = f'{mute_value}'
                    self.update_bottom_knob_value(i, bottom_text)
            #This isn't working yet          
            elif self.func == 5:
                self.control_mode = "Select"
                #logging.debug(f'KEYSTAGE DRIVER {self.control_mode}')
                for i in range(0, num_of_chains):
                    mixer_chan = self.get_mixer_chan_from_device_col(i)
                    if self.rec_mode:
                        active_chain_index = mixer_chan
                        #logging.debug(f'KEYSTAGE DRIVER : active chain index is : {mixer_chan}')
                    #if self.zynmixer.get_active(i):
                        active_value = 'Active'
                    else:
                        active_value = ' '
                    bottom_text = f'{active_value}'
                    self.update_bottom_knob_value(i, bottom_text)
            elif self.func == 6:
                self.control_mode = "ZynthianUI"
                knob_names = ["Layer", "Back"," ", " ", "Snapshot", "Select", " ", " "]
                for i in range(0, 8):
                    self.korg_keystage_display_data2(i+1,0,knob_names[i])
        elif self.func == 7:
            self.control_mode = "Device"
            self.state_manager.send_cuia("CHAIN_CONTROL")
            self.update_device_mode_ctrl_display()
           #self.device_mode_handler()        
        elif self.func > 7:
            self.func = 0
            self.control_mode = "Chain"
            self.control_mode_handler(self.func)
            #self.chain_mode_display()
        #    self.control_mode = "Chain" 
        elif self.func < 0:
            self.func = 7
            self.control_mode = "Device"
            self.state_manager.send_cuia("CHAIN_CONTROL")
            self.control_mode_handler(self.func)
            #self.update_device_mode_ctrl_display()           
        self.korg_keystage_display_data2(0,0,self.control_mode)
        #self.chain_name_handler()

    def chain_name_handler(self,*chain_name):
        #logging.debug(f'KEYSTAGE DRIVER : chain_name_handler: chain:{self}')
        #chain_id = None
        #chainy = None
        if self.midimix_bank:
            col0 = 8
        else:
            col0 = 0
        #self.korg_keystage_display_data2(1,0,chain_id)
        for i in range(0, 8):
            chain_name = ' '
            chain = self.get_chain_by_position(col0 + i)
            if chain is not None:
                chain_id_str = str(self.chain_manager.get_chain_id_by_index(col0 + i))
                chain_id = self.chain_manager.get_chain_id_by_index(col0 + i)
                #try:
                    #chain_name = str(chain_id.get_title())
                #chain_name = str(self.chain_manager.get_chain_id_by_index(col0 + i).get_title())
                #except:
                #    chain_name = ''
                #logging.debug(f'Chain ID by Index is: {chain_id}')
                #chain_id = str(self.chain_manager.get_chain_id_by_index(col0 + i))
                #chain_name = str(self.chain.get_description(1))
                chain_name = str(chain.get_title())
                #logging.debug(f'Chain name is: {chain_name}')
                #chain_id = "1234567891011121314151617181920"
            #else:
                #chain_name = ' '
            self.korg_keystage_display_data2(self.native_knobs_ccnum[i]+1,0,chain_name)

    #This isnt being used yet - its breaking something when called
    def device_mode_handler(self, ccnum = None, ccval = None):
        # Get screen info  
        #self.zyn_gui_ctrl = zynthian_gui_control
        self.ccvals_full = ccval
   
        self.screen_processor = self.chain_manager.get_active_chain().current_processor
        self.current_processor = self.screen_processor
        
        #trying to get current controllers again
        self.current_screen_index = self.current_processor.get_current_screen_index()
        self.init_ctrl_screens = self.current_processor.init_ctrl_screens()
        self.get_ctrl_screens = self.current_processor.get_ctrl_screens()
        self.screen_title = list(self.get_ctrl_screens)[self.current_screen_index-1]

        self.zcontrollers = self.screen_processor.get_ctrl_screen(self.screen_title)

        #Lot fo Logging!
        #logging.debug(f'KEYSTAGE DRIVER : CURRENT PROCESSOR IS : {dir(self.current_processor)}')
        #logging.debug(f'KEYSTAGE DRIVER : dir of SCREEN PROCESSOR IS : {dir(self.screen_processor)}')
        #logging.debug(f'KEYSTAGE DRIVER : SCREEN PROCESSOR IS : {vars(self.screen_processor)}')
        #logging.debug(f'KEYSTAGE DRIVER : SCREEN PROCESSOR NAME? IS : {(self.screen_processor.get_ctrl_screen(self.current_screen_index))}')
        #logging.debug(f'KEYSTAGE DRIVER : CURRENT SCREEN INDEX IS : {self.current_screen_index}')
        #logging.debug(f'KEYSTAGE DRIVER : init_ctrl_screens : {self.init_ctrl_screens}')
        #logging.debug(f'KEYSTAGE DRIVER : get_ctrl_screens : {self.get_ctrl_screens}')
        #logging.debug(f'KEYSTAGE DRIVER :  dir of get_ctrl_screens : {dir(self.get_ctrl_screens)}')
        #logging.debug(f'KEYSTAGE DRIVER : current screen title : {list(self.get_ctrl_screens)[self.current_screen_index]}')
        #logging.debug(f'KEYSTAGE DRIVER : zcontrollers : {self.zcontrollers}')
        #logging.debug(f'KEYSTAGE DRIVER : CURRENT SCREEN INDEX IS : {dir(self.current_screen_index)}')
        #logging.debug(f'KEYSTAGE DRIVER : CONTROLLER SCREEN IS : {self.screen_title}')
        knobs = []
        knob_values = []
        for j in range(4):
            if j < len(self.zcontrollers):
                ctrl = self.zcontrollers[j]
                knob = ctrl.short_name
                if ctrl.value2label is not None:
                    knob_value = str(ctrl.value2label[str(int(ctrl.value))])
                else:
                    knob_value = str(ctrl.value)[:5]                 
            else:
                knob = ""
                knob_value = ""
            knobs.append(knob)
            knob_values.append(knob_value)
            
        knob_names = [knobs[0], knobs[1], " ",self.screen_title, knobs[2], knobs[3]," ", " "]
        ctrl_values = [knob_values[0], knob_values[1], " ", " ", knob_values[2], knob_values[3]," ", " "]
        
        for i in range(0, 8):
            self.korg_keystage_display_data2(i+1,0,knob_names[i])
            self.korg_keystage_display_data2(i+1,1,ctrl_values[i]) 

        #Code for dealing with rotary controls instead of encoders
        if ccnum is None:
            return
        else:
            col = self.native_knobs_ccnum.index(ccnum)
        #delta = self._knobs_ease.feed(ccnum, ccval, self._is_shifted)
        if ccval is None:
            return       
        if ccval == 0:
            delta = -63

        elif ccval == 127:
            delta = 63
        
        elif strictly_decreasing(self.ccvals_full):
            delta = -1
      
        elif strictly_increasing(self.ccvals_full):
            delta = 1
                                                       
        if delta is None:
            return

        zynpot = {
            self.KNOB_LAYER: 0,
            self.KNOB_BACK: 2,
            self.KNOB_SNAPSHOT: 1,
            self.KNOB_SELECT: 3
            }.get(ccnum, None)
        if zynpot is None:
            return 

        #self.state_manager.send_cuia("ZYNPOT", [zynpot, delta])
        self.state_manager.send_cuia("ZYNPOT_ABS", [zynpot, ccval/127])

    def update_device_mode_ctrl_display(self):
        logging.debug(f'KEYSTAGE DRIVER : RUNNING FROM UDMCD - Wait 0.1s')
        #added delay to prevent get active chain processor executing before CUIA call to change processor 
        sleep(0.1)
        logging.debug(f'KEYSTAGE DRIVER :  RUNNING FROM UDMCD - Continuing')
        # Get screen info  
        #self.zyn_gui_ctrl = zynthian_gui_control
       
        screen_processor = self.chain_manager.get_active_chain().current_processor
        current_processor = screen_processor
        
        current_screen_index = current_processor.get_current_screen_index()
        #init_ctrl_screens = 
        current_processor.init_ctrl_screens()
        get_ctrl_screens = current_processor.get_ctrl_screens()
        screen_title = list(get_ctrl_screens)[current_screen_index-1]

       #self.zcontrollers = self.screen_processor.get_ctrl_screen(self.screen_title)
        zcontrollers = current_processor.get_ctrl_screen(screen_title)
        logging.debug(f'KEYSTAGE DRIVER : Current Chain is : {self.chain_manager.get_active_chain().get_title}\n Screen Processor is {screen_processor.name}\n Current Processor is : {current_processor.name}\n Current Screen Index is : {current_screen_index}\n Current Screen Title is : {screen_title}')

        knobs = []
        knob_values = []
        for j in range(4):
            if j < len(zcontrollers):
                ctrl = zcontrollers[j]
                knob = ctrl.short_name
                if ctrl.value2label is not None:
                    knob_value = str(ctrl.value2label[str(int(ctrl.value))])
                else:
                    knob_value = str(ctrl.value)[:5]                 
            else:
                knob = ""
                knob_value = ""
            knobs.append(knob)
            knob_values.append(knob_value)

            #knob_res_calc(ctrl.value_min, ctrl.value_max, ctrl.value_mid, ctrl.value_range)
        knob_names = [knobs[0], knobs[1], str(current_screen_index-1), screen_title, knobs[2], knobs[3]," ", " "]
        ctrl_values = [knob_values[0], knob_values[1], " ", " ", knob_values[2], knob_values[3]," ", " "]
        
        for i in range(0, 8):
            self.korg_keystage_display_data2(i+1,0,knob_names[i])
            self.korg_keystage_display_data2(i+1,1,ctrl_values[i])
        return True

    def midi_event(self, ev):
        evtype = (ev[0] >> 4) & 0x0F
        if evtype == 0xB:
            ccnum = ev[1] & 0x7F
            ccval = ev[2] & 0x7F
            ccchan = ev[0] - 176
            #Uncomment for CC midi event monitor
            #logging.debug(f' CC Type {evtype}, CC Chan {ccchan}, CC Num {ccnum}, CC Val {ccval}')

            num_of_chains = len(self.chain_manager.chains)
            ccval_res = int(((ccval + 1) / 128) * num_of_chains)
            ccval_full = ccval 
            if self.ccvals_full is not None:         
                del self.ccvals_full[:-2]
                self.ccvals_full.append(ccval_full)
                del self.ccvals_full[:-2]
            else:
                return True
            if self.ccvals is not None:    
                del self.ccvals[:-2]
                self.ccvals.append(ccval_res) 
                del self.ccvals[:-2]
            else:
                return True  
            if ccnum == self.native_value_knob_left_ccnum:
                if ccval > 0:
                    if self.func == 0:
                        self.func = 7
                    else:
                        self.func = self.func - 1
                    self.control_mode_handler(self.func)
                    logging.debug(f'KEYSTAGE DRIVER : ccval: {ccval} Func : {self.func}')
                    self.refresh()
                return True
            elif ccnum == self.native_value_knob_right_ccnum:
                if ccval > 0:                
                    self.func = self.func + 1                   
                    self.control_mode_handler(self.func)
                    logging.debug(f'KEYSTAGE DRIVER : ccval: {ccval} Func : {self.func}')
                    self.refresh()                
                return True
            elif ccnum == self.native_previous_track_ccnum:
                if ccval > 0:
                    self.state_manager.send_cuia("ARROW_LEFT")
                    self.refresh()
                return True
            elif ccnum == self.native_next_track_ccnum:
                if ccval > 0:
                    self.state_manager.send_cuia("ARROW_RIGHT")
                    self.refresh()
                return True
            elif ccnum == self.native_cycle_ccnum:
                if ccval > 0:
                    self.shift = not self.shift
                    self.rec_mode = self.shift
                    self.refresh()
                return True
            elif ccnum == self.native_val_up_ccnum:
                if ccval > 0:
                    self.state_manager.send_cuia("ARROW_UP")
                    self.update_device_mode_ctrl_display()
                    self.refresh()
                    # if self.control_mode == "Device":
                    #     self.state_manager.send_cuia("ARROW_UP")
                    #     logging.debug(f'Arrow Up')
                    #     self.update_device_mode_ctrl_display()
                    # else:
                    #     self.state_manager.send_cuia("ARROW_UP")
                    #self.refresh()
                return True
            elif ccnum == self.native_val_down_ccnum:
                if ccval > 0:
                    self.state_manager.send_cuia("ARROW_DOWN")
                    self.update_device_mode_ctrl_display()
                    self.refresh()
                    # if self.control_mode == "Device":
                    #     self.state_manager.send_cuia("ARROW_DOWN")
                    #     logging.debug(f'Arrow Down')
                    #     self.update_device_mode_ctrl_display()
                    # else:
                    #     self.state_manager.send_cuia("ARROW_DOWN")
                    #self.refresh()
                return True
            elif ccnum == self.native_undo_ccnum:
                if ccval > 0:
                    self.state_manager.send_cuia("ZYNSWITCH", [3, "P"])
                else:
                    self.state_manager.send_cuia("ZYNSWITCH", [3, "R"])
                self.refresh()
                return True
            elif ccnum == self.native_transport_frwd_ccnum:
                if ccval > 0:
                    if self.midimix_bank == 0:
                        self.state_manager.send_cuia("BACK")
                    else:
                        self.midimix_bank = 0
                    self.refresh()
                return True
            elif ccnum == self.native_transport_ffwd_ccnum:
                if ccval > 0:
                    self.midimix_bank = 1
                    self.refresh()
                return True
            elif ccnum == self.native_transport_play_ccnum:
                if ccval > 0:
                    if self.shift:
                        self.state_manager.send_cuia("TOGGLE_MIDI_PLAY")
                    else:
                        self.state_manager.send_cuia("TOGGLE_AUDIO_PLAY")
                return True
            elif ccnum == self.native_transport_rec_ccnum:
                if ccval > 0:
                    if self.shift:
                        self.state_manager.send_cuia("TOGGLE_MIDI_RECORD")
                    else:
                        self.state_manager.send_cuia("TOGGLE_AUDIO_RECORD")
                return True
            elif ccnum == self.native_transport_stop_ccnum:
                if ccval > 0:
                    if self.shift:
                        self.state_manager.send_cuia("STOP_MIDI_PLAY")
                    else:
                        self.state_manager.send_cuia("STOP_AUDIO_PLAY")
                return True
            # TOGGLE NATIVE/NORMAL MODE
            elif ccnum == self.native_exit_ccnum and ccchan == self.midi_chan:
                if self.native_mode == True:
                    self.set_mode_normal()
                else:
                    self.set_mode_native()
                return True
            # Chain mode in progress
            elif self.control_mode == 'Chain' and ccnum in self.native_knobs_ccnum:
                #if ccnum not in self.native_knobs_ccnum:
                #    return True
                col = self.native_knobs_ccnum.index(ccnum)
                active_chain2 = self.chain_manager.get_active_chain()
                active_chain_id = self.chain_manager.active_chain_id
                active_chain_name = str(active_chain2.get_title())
                active_chain_index = self.chain_manager.get_chain_index(active_chain_id)        
                mixer_chan = self.get_mixer_chan_from_device_col(active_chain_index)
                #ACTIVE CHAIN SELECTION
                if col == 0:
                    #Knob acts as encoder and changes active chain - May need to adjust resolution so channels are more easily selected - only tested with 2 so far.
                    if strictly_decreasing(self.ccvals):
                        self.state_manager.send_cuia("ARROW_LEFT")
                    elif strictly_increasing(self.ccvals):
                        self.state_manager.send_cuia("ARROW_RIGHT")
                    self.update_bottom_knob_value(col, active_chain_name)
                    self.chain_mode_display()
                # ADJUST VOLUME
                elif col == 1:
                    if mixer_chan is not None:
                        self.zynmixer.set_level(
                            mixer_chan, ccval / 127.0, True)
                        level_value = self.zynmixer.get_level(mixer_chan)
                        if level_value == 0:
                            level_db = f'-infinity dB'
                        else: 
                            level_db = f'{round(20 * log10(level_value),2)}dB'
                        bottom_text = str(level_db)
                        self.update_bottom_knob_value(col, bottom_text)
                # ADJUST PAN
                elif col == 2:
                    if ccval >= 0:
                        if mixer_chan is not None:
                            self.zynmixer.set_balance(
                                mixer_chan, 2.0 * ccval/127.0 - 1.0)
                            balance_value = self.zynmixer.get_balance(mixer_chan)
                        if balance_value == 0:
                            bottom_text = '<C>'
                        else:
                            bottom_text = f'{round(balance_value * 100, 0)}%'
                        self.update_bottom_knob_value(col, bottom_text)
                # ADJUST SOLO
                elif col == 3:
                    if ccval >= 0:
                        if mixer_chan is not None:
                            if self.zynmixer.get_solo(mixer_chan):
                                val = 0
                                bottom_text = ' '
                            else:
                                val = 1
                                bottom_text =  'On'
                            self.zynmixer.set_solo(mixer_chan, val, True)
                            self.update_bottom_knob_value(col, bottom_text)
                # ADJUST MUTE
                elif col == 4:
                    if ccval >= 0:
                        if mixer_chan is not None:
                            if self.zynmixer.get_mute(mixer_chan):
                                val = 0
                                bottom_text = ' '
                            else:
                                val = 1
                                bottom_text =  'On'
                            self.zynmixer.set_mute(mixer_chan, val, True)
                            self.update_bottom_knob_value(col, bottom_text)
                self.refresh()            
                return True
            #VOLUME MODE
            elif self.control_mode == 'Volume' and ccnum in self.native_knobs_ccnum:
                #if ccnum not in self.native_knobs_ccnum:
                #    return
                col = self.native_knobs_ccnum.index(ccnum)    
                # With "shift" ...
                if self.shift and col == 7:
                    # use last fader to control Main volume (right)
                    self.zynmixer.set_level(255, ccval / 127.0)
                    level_value = self.zynmixer.get_level(255)
                    if level_value is not None:
                        if level_value == 0:
                            level_db = f'-infinity dB' 
                        else:
                            level_db = f'{round(20 * log10(level_value),2)}dB'
                        bottom_text = str(level_db)
                        self.update_bottom_knob_value(col, bottom_text)
                # else, use faders to control chain's volume
                else:
                    mixer_chan = self.get_mixer_chan_from_device_col(col)
                    if mixer_chan is not None:
                        self.zynmixer.set_level(
                            mixer_chan, ccval / 127.0, True)
                        level_value = self.zynmixer.get_level(mixer_chan)
                        if level_value == 0:
                            level_db = f'-infinity dB'
                        else: 
                            level_db = f'{round(20 * log10(level_value),2)}dB'
                        bottom_text = str(level_db)
                        self.update_bottom_knob_value(col, bottom_text)
                return True           
            # PAN MODE
            elif self.control_mode == 'Pan' and ccnum in self.native_knobs_ccnum:
                #if ccnum not in self.native_knobs_ccnum:
                #    return
                col = self.native_knobs_ccnum.index(ccnum)
                # With "shift" ...
                if self.shift:
                    # use last knob to control Main balance
                    if col == 7:
                        self.zynmixer.set_balance(
                            255, 2.0 * ccval / 127.0 - 1.0)
                        balance_value = self.zynmixer.get_balance(255)
                        if balance_value == 0:
                            bottom_text = '<C>'
                        else: 
                            bottom_text = f'{round(balance_value * 100, 0)}%'
                        self.update_bottom_knob_value(col, bottom_text)
                    # pass rest of knob's CC to engine control (MIDI-learn)
                    else:
                        return False
                # else, use knobs to control chain's balance
                else:
                    mixer_chan = self.get_mixer_chan_from_device_col(col)
                    if mixer_chan is not None:
                        self.zynmixer.set_balance(
                            mixer_chan, 2.0 * ccval/127.0 - 1.0)
                        balance_value = self.zynmixer.get_balance(mixer_chan)
                        if balance_value == 0:
                            bottom_text = '<C>'
                        else:
                            bottom_text = f'{round(balance_value * 100, 0)}%'
                        self.update_bottom_knob_value(col, bottom_text)
                return True
            # MUTE MODE
            elif self.control_mode == 'Mute' and ccnum in self.native_knobs_ccnum:
                if ccval > 64:
                    col = self.native_knobs_ccnum.index(ccnum)
                    if self.shift and col == 7:
                        mixer_chan = 255
                    else:
                        mixer_chan = self.get_mixer_chan_from_device_col(col)
                    if mixer_chan is not None:
                        if self.zynmixer.get_mute(mixer_chan):
                            val = 0
                            bottom_text = ' '
                        else:
                            val = 1
                            bottom_text = 'Mute'
                        self.zynmixer.set_mute(mixer_chan, val, True)
                        # Send LED feedback
                        if self.idev_out is not None:
                            lib_zyncore.dev_send_ccontrol_change(
                                self.idev_out, self.midi_chan, ccnum, val * 0x7F)
                            self.update_bottom_knob_value(col, bottom_text)
                    elif self.idev_out is not None:
                        # If not associated mixer channel, turn-off the led
                        lib_zyncore.dev_send_ccontrol_change(
                            self.idev_out, self.midi_chan, ccnum, 0)
                        self.update_bottom_knob_value(col, bottom_text)
                return True
           #SOLO MODE
            elif self.control_mode == 'Solo' and ccnum in self.native_knobs_ccnum:
                if ccval > 64:
                    col = self.native_knobs_ccnum.index(ccnum)
                    if self.shift and col == 7:
                        mixer_chan = 255
                    else:
                        mixer_chan = self.get_mixer_chan_from_device_col(col)
                    if mixer_chan is not None:
                        if self.zynmixer.get_solo(mixer_chan):
                            val = 0
                            bottom_text = ' '
                        else:
                            val = 1
                            bottom_text = 'Solo'
                        self.zynmixer.set_solo(mixer_chan, val, True)
                        # Send LED feedback
                        if self.idev_out is not None:
                            lib_zyncore.dev_send_ccontrol_change(
                                self.idev_out, self.midi_chan, ccnum, val * 0x7F)
                            self.update_bottom_knob_value(col, bottom_text)
                    elif self.idev_out is not None:
                        # If not associated mixer channel, turn-off the led
                        lib_zyncore.dev_send_ccontrol_change(
                            self.idev_out, self.midi_chan, ccnum, 0)
                        self.update_bottom_knob_value(col, bottom_text)
                return True
            #SELECT/ARM MODE
            elif self.control_mode == 'Select' and ccnum in self.native_knobs_ccnum:
                if ccval > 0:
                    col = self.native_knobs_ccnum.index(ccnum)
                    if not self.rec_mode:
                        if self.midimix_bank:
                            col += 8
                        self.chain_manager.set_active_chain_by_index(col)
                        bottom_text = 'Active'
                        self.refresh()
                    else:
                        mixer_chan = self.get_mixer_chan_from_device_col(col)
                        if mixer_chan is not None:
                            self.state_manager.audio_recorder.toggle_arm(
                                mixer_chan)
                            # Send LED feedback
                            if self.idev_out is not None:
                                val = self.state_manager.audio_recorder.is_armed(
                                    mixer_chan) * 0x7F
                                bottom_text = ' '
                                lib_zyncore.dev_send_ccontrol_change(
                                    self.idev_out, self.midi_chan, ccnum, val)
                        elif self.idev_out is not None:
                            # If not associated mixer channel, turn-off the led
                            bottom_text = ' '
                            lib_zyncore.dev_send_ccontrol_change(
                                self.idev_out, self.midi_chan, ccnum, 0)
                    for i in range(0, 8):
                        self.update_bottom_knob_value(i, ' ')
                    self.update_bottom_knob_value(col, bottom_text)
                return True
            # DEVICE MODE
            # not working propery yet need to fix - May need to set this up as a seperate class from Zynmixer
            # We may be able to get zynpot names from zynthian_gui_control, but code copied across for now
            elif self.control_mode == 'Device':
                logging.debug(f' KEYSTAGE DRIVER : RUNNING FROM MIDI_EVENT')
                #self.ccvals_full = self.restrict_range(ccval)
                # Get screen info
                #self.zynthian_gui_control.get_screen_info()
                #self.current_screen_info = self.zyn_gui_ctl().get_screen_info()
                #self.list = self.zyn_gui_ctl.fill_list()
                #logging.debug(f'KEYSTAGE DRIVER : CONTROLLER LIST : {self.list}')
                #self.screen_title = self.current_screen_info.screen_title
                #self.current_processor = self.chain_manager.get_active_chain().current_processor
                #self.current_screen_index = self.current_processor.get_current_screen_index()   
                #zyn_gui_ctrl = zynthian_gui_control
                #self.zcontrollers = self.zyn_gui_ctrl

                #lets set up or get the screen info we need
                """
                try:
                    self.a = zynthian_gui_control.fill_list
                    self.c = self.zyn_gui_ctrl.fill_list
                except:
                    logging.debug(f'KEYSTAGE DRIVER :  a That didnt work')
                else:
                    #logging.debug(f'self.a is : {dir(self.a)}')
                    #logging.debug(f'self.c is : {vars(self.c)}')
                    pass
                    
                #for i in range(4):
                try:
                    self.b = zynthian_gui_control.get_zcontroller(0)
                except:
                    logging.debug(f'KEYSTAGE DRIVER : b That didnt work')
                else:
                    logging.debug(f'self.b is : {self.b}')
                """
                #Trying to get screen info again!
                screen_processor = self.chain_manager.get_active_chain().current_processor
                current_processor = screen_processor

                """
                #copy fill_list function to mess with

                #def fill_list(self):
                self.list_data = []
                # Configure processors if needed
                #urproc = self.zyngui.get_current_processor()
                curproc = self.current_processor()
                self.configure_processors(curproc)

                if not self.processors:
                    self.list_data.append((None, None, "NO PROCESSORS!"))
                else:
                    i = 0
                    for processor in self.processors:
                        j = 0
                        screen_list = processor.get_ctrl_screens()
                        self.list_data.append((None, None, f"> {processor.engine.name.split('/')[-1]}"))
                        for cscr in screen_list:
                            self.list_data.append((screen_list[cscr][0].group_symbol, i, cscr, processor, j))
                            i += 1
                            j += 1
                        self.index = curproc.get_current_screen_index()
                        self.get_screen_info()
                #super().fill_list()
                """
                #trying to get current controllers again
                current_screen_index = current_processor.get_current_screen_index()
                #init_ctrl_screens = 
                current_processor.init_ctrl_screens()
                get_ctrl_screens = current_processor.get_ctrl_screens()
                screen_title = list(get_ctrl_screens)[current_screen_index-1]

                zcontrollers = screen_processor.get_ctrl_screen(screen_title)

                #logging.debug(f'KEYSTAGE DRIVER : CURRENT PROCESSOR IS : {dir(self.current_processor)}')
                #logging.debug(f'KEYSTAGE DRIVER : dir of SCREEN PROCESSOR IS : {dir(self.screen_processor)}')
                #logging.debug(f'KEYSTAGE DRIVER : SCREEN PROCESSOR IS : {vars(self.screen_processor)}')
                #logging.debug(f'KEYSTAGE DRIVER : SCREEN PROCESSOR NAME? IS : {(self.screen_processor.get_ctrl_screen(self.current_screen_index))}')
                logging.debug(f'KEYSTAGE DRIVER : CURRENT SCREEN INDEX IS : {current_screen_index-1}')
                #logging.debug(f'KEYSTAGE DRIVER : init_ctrl_screens : {init_ctrl_screens}')
                #logging.debug(f'KEYSTAGE DRIVER : get_ctrl_screens : {self.get_ctrl_screens}')
                #logging.debug(f'KEYSTAGE DRIVER :  dir of get_ctrl_screens : {dir(self.get_ctrl_screens)}')
                logging.debug(f'KEYSTAGE DRIVER : current screen title : {list(get_ctrl_screens)[current_screen_index]}')
                logging.debug(f'KEYSTAGE DRIVER : zcontrollers : {dir(zcontrollers)}')
                #logging.debug(f'KEYSTAGE DRIVER : CURRENT SCREEN INDEX IS : {dir(self.current_screen_index)}')
                logging.debug(f'KEYSTAGE DRIVER : CONTROLLER SCREEN IS : {screen_title}')
                knobs = []
                knob_values = []
                for j in range(4):
                    if j < len(zcontrollers):
                        ctrl = zcontrollers[j]
                        logging.debug(f'KEYSTAGE DRIVER : Controller : {ctrl.short_name}')
                        #for attr in dir(ctrl):     
                            #logging.debug(f'{attr, getattr(ctrl, attr)}')
                        knob = ctrl.short_name
                        #knob_value = str(ctrl.value)
                        if ctrl.value2label is not None:
                            #for attr in dir(ctrl.value2label):     
                                #logging.debug(f'{attr, getattr(ctrl.value2label, attr)}')
                            #knob_value = str(ctrl.value2label[0])
                            #logging.debug(f'Value2label keys : {ctrl.value2label}')
                            #logging.debug(f'Value2label : {ctrl.value2label[str(int(ctrl.value))]}')
                            knob_value = str(ctrl.value2label[str(int(ctrl.value))])
                        else:
                            knob_value = str(ctrl.value)[:5]
                    else:
                        knob = ""
                        knob_value = ""
                    knobs.append(knob)
                    knob_values.append(knob_value)
                    
                logging.debug(f'KEYSTAGE DRIVER : Knobs {knobs}')

                knob_names = [knobs[0], knobs[1], str(current_screen_index), screen_title, knobs[2], knobs[3]," ", " "]
                ctrl_values = [knob_values[0], knob_values[1], " ", " ", knob_values[2], knob_values[3]," ", " "]

                #UPDATE KNOB NAMES and VALUES ON KEYSTAGE DISPLAY
                for i in range(0, 8):
                    self.korg_keystage_display_data2(i+1,0,knob_names[i])
                    self.korg_keystage_display_data2(i+1,1,ctrl_values[i])

                #Dirty Error handling for < 4 controllers on a screen
                zctrl = ["","","","","","","",""]
                j =  len(zcontrollers)
                for k in range (j):
                    zctrl[k] = zcontrollers[k]
                    
                if ccnum not in self.native_knobs_ccnum:
                    return
                else:                       
                    col = self.native_knobs_ccnum.index(ccnum)
                    #ctrl_map = [zcontrollers[0], zcontrollers[1], "", "", zcontrollers[2], zcontrollers[3]]
                    ctrl_map = [zctrl[0], zctrl[1], "", "", zctrl[2], zctrl[3]]
                    col2ctrl = dict(zip(self.native_knobs_ccnum, ctrl_map))
                    if col2ctrl[col] is not None:
                        #logging.debug(f'col2ctl :  {col2ctrl[col].short_name}')
                        ctrl = col2ctrl[col]
                        ccvals_ctrl_res = self.restrict_range_controller(ctrl, ccval)
                    else:
                        return
                    #knob_res_calc(ctrl.value_min, ctrl.value_max, ctrl.value_mid, ctrl.value_range)
                    
                #delta = self._knobs_ease.feed(ccnum, ccval, self._is_shifted)
                delta = None
                if ccval is None:
                    return 
                                               
                elif ccval == 0:
                    delta = -63

                elif ccval == 127:
                    delta = 63
                
                elif strictly_decreasing(ccvals_ctrl_res):
                    logging.debug(f'KEYSTAGE DRIVER : Knob is Decreasing')
                    delta = -1
                elif strictly_increasing(ccvals_ctrl_res):
                    logging.debug(f'KEYSTAGE DRIVER : Knob is Increasing')
                    delta = 1

                if delta is None:
                    return

                zynpot = {
                    self.KNOB_LAYER: 0,
                    self.KNOB_BACK: 2,
                    self.KNOB_SNAPSHOT: 1,
                    self.KNOB_SELECT: 3
                    }.get(ccnum, None)
                if zynpot is None:
                   return 
                #self.state_manager.send_cuia("ZYNPOT", [zynpot, delta])
                self.state_manager.send_cuia("ZYNPOT_ABS", [zynpot, ccval/127])
                return True
            elif self.control_mode == 'ZynthianUI':
                knob_names = ["Layer", "Back"," ", " ", "Snapshot", "Select", " ", " "]
                #UPDATE KNOB NAMES and VALUES ON KEYSTAGE DISPLAY
                for i in range(0, 8):
                    self.korg_keystage_display_data2(i+1,0,knob_names[i])
                    #self.korg_keystage_display_data2(i+1,1,ctrl_values[i])
                if ccnum is None:
                    return
                else:
                    #col = self.native_knobs_ccnum.index(ccnum)
                    #ctrl_values = [knob_values[0], knob_values[1], " ", " ", knob_values[2], knob_values[3]," ", " "]
               
                    #if ccnum is None:
                    #    return
                    zynpot = {
                    self.KNOB_LAYER: 0,
                    self.KNOB_BACK: 2,
                    self.KNOB_SNAPSHOT: 1,
                    self.KNOB_SELECT: 3
                    }.get(ccnum, None)
                    if zynpot is None:
                        return 
                    self.state_manager.send_cuia("ZYNPOT_ABS", [zynpot, ccval/127])               
                return True
            # SysEx
        elif ev[0] == 0xF0:
            if callable(self.sysex_answer_cb):
                self.sysex_answer_cb(ev)
            else:
                logging.debug(f"KEYSTAGE DRIVER : Received SysEx (unprocessed) => {ev.hex(' ')}")
            return True
        # elif ev[0] == 0xFA:
        #     if callable(self.sysex_answer_cb):
        #         self.sysex_answer_cb(ev)
        #     else:
        #         logging.debug(f"START => {ev.hex(' ')}")
        #     return True
        # elif ev[0] == 0xFC:
        #     if callable(self.sysex_answer_cb):
        #         self.sysex_answer_cb(ev)
        #     else:
        #         logging.debug(f"STOP => {ev.hex(' ')}")
        #     return True
        # elif ev[0] == 0xFB:
        #     if callable(self.sysex_answer_cb):
        #         self.sysex_answer_cb(ev)
        #     else:
        #         logging.debug(f"CONTINUE => {ev.hex(' ')}")
        #     return True
        
    def zynthianui_mode(self):
        pass

    # Light-Off all LEDs
    def light_off(self):
        if self.idev_out is None:
            return

        for ccnum in self.mute_ccnums:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, ccnum, 0)
        for ccnum in self.solo_ccnums:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, ccnum, 0)
        for ccnum in self.rec_ccnums:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, ccnum, 0)
        #added 63 to see if it would negate log error
        for ccnum in [41, 42, 43, 44, 45, 46, 58, 59, 60, 61, 62]:
            lib_zyncore.dev_send_ccontrol_change(
                self.idev_out, self.midi_chan, ccnum, 0)

    def send_sys_real(self, data):
        if self.idev_out is not None:
            msg = bytes.fromhex(
                #f"F0 42 4{hex(self.midi_chan)[2:]} 00 01 69 09 02 00 00 00 00 F7")
                f"{data}")
            lib_zyncore.dev_send_midi_event(self.idev_out, msg, len(msg))
            logging.debug(f"KEYSTAGE DRIVER : System Realtime Message sent : {msg}")

    def restrict_range(self, ccval):
    #Used for restricting resolution of CC for mixer channel selection - may want to move this elsewhere
        logging.debug(f'KEYSTAGE DRIVER : ccval is :  {ccval}')
        num_of_chains = len(self.chain_manager.chains)
        ccval_res = int(((ccval + 1) / 128) * num_of_chains)
        ccval_full = ccval 
        del self.ccvals[:-2]
        del self.ccvals_full[:-2]
        self.ccvals.append(ccval_res)
        self.ccvals_full.append(ccval_full)
        del self.ccvals[:-2]
        del self.ccvals_full[:-2]
        return True
            #self.ccvals[-5:]
            #logging.debug(f'KEYSTAGE DRIVER : ccvals_res list is :{self.ccvals}')
            #logging.debug(f'KEYSTAGE DRIVER : ccvals_full list is :{self.ccvals_full}')

    def restrict_range_controller(self, ctrl, ccval):
        knob = ctrl.short_name
        if knob != knob:
            self.ccvals_ctrl_res = []
        else:
            pass 
        if ctrl.is_integer:
            ccval_ctrl_res = int(((ccval + 1) / 128) * ctrl.value_range)
            logging.debug(f'KEYSTAGE DRIVER : if ctrl.is_integer : TRUE :{ctrl.short_name} {ccval_ctrl_res}')
        else:
            ccval_ctrl_res = ccval
            logging.debug(f'KEYSTAGE DRIVER : if ctrl.is_integer : FALSE :{ctrl.short_name} {ccval_ctrl_res}')
            #ccval_full = ccval 
            del self.ccvals_ctrl_res[:-2]
            self.ccvals_ctrl_res.append(ccval_ctrl_res)
            del self.ccvals_ctrl_res[:-2]
            logging.debug(f'KEYSTAGE DRIVER : Knob : {knob}, ccval : {ccval}, ccval_ctrl_res :{ccval_ctrl_res}, ccvals_ctrl_res {self.ccvals_ctrl_res}')
        return self.ccvals_ctrl_res

# ------------------------------------------------------------------------------

#------------------------------------------------------------------------------#
#    Class to duplicate transport controls to System Realtime midi messages    #
#------------------------------------------------------------------------------#

# class TransportToSystemRealtime:

#     start = "FA"
#     stop = "FC"
#     resume = "FB"

#     def __init__(self, state_manager, idev_in, idev_out=None):
#         super().__init__(state_manager, idev_in, idev_out)
    
#     def send_sys_real(self, data):
#         if self.idev_out is not None:
#             msg = bytes.fromhex(
#                 #f"F0 42 4{hex(self.midi_chan)[2:]} 00 01 69 09 {data} F7")
#                 f"{data}")
#             lib_zyncore.dev_send_midi_event(self.idev_out, msg, len(msg))

#Functions to use rotarty pots and encoders

def strictly_increasing(L):
    """Returns TRUE if the values in the list are strictly increasing
    Always increasing; never remaining constant or decreasing or null.
    """ 
    return all(x<y for x, y in zip(L, L[1:]))


def strictly_decreasing(L):
    """Returns TRUE if the values in the list are strictly decreasing
    Always decreasing; never remaining constant or increasing or null.
    """ 
    return all(x>y for x, y in zip(L, L[1:]))
  
def non_decreasing(L):
    """Returns TRUE if values in the list are increasing.
    Allows for values remaining constant. Does NOT allow null
    """
    return all(x<=y for x, y in zip(L, L[1:]))


def non_increasing(L):
    """Returns TRUE if values in the list are decreasing.
    Allows for values remaining constant. Does NOT allow null
    """
    return all(x>=y for x, y in zip(L, L[1:]))


def not_strictly_increasing(L):
    # strip leading null values
    while len(L)!=0 and L[0] is None: L.pop(0)
    # check list has monotonically increasing values
    # this returns TRUE if values are increasing
    strictly_increasing = all(x<y for x, y in zip(L, L[1:]))
    # invert the return value
    return not(strictly_increasing)

def rotary_to_encoder_test(a):
    ccvals = a
    #ccvals.append(a)
    logging.debug(f'KEYSTAGE DRIVER : a is : {ccvals}')
    x = zip(ccvals, ccvals[1:])
    y = zip(str(25), str(26))
    logging.debug(f'KEYSTAGE DIRVER : tuple is : {tuple(x)}')
    logging.debug(f'KEYSTAGE DRIVER : dummy tuple is : {tuple(y)}')

def knob_res_calc(min, max, mid, range):
    logging.debug(f'KEYSTAGE DRIVER {min}, {max}, {mid}, {range}')



