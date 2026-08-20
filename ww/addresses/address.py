"""
Wind Waker (JP) – base addresses and offsets.

Keep names stable so other modules (link.py, camera.py, collision.py) don’t break if we swap regions.
"""
from ..context.regional_value import RegionalValue


class Address:
    # Game / engine timing
    FRAME_COUNTER_ADDRESS: int = RegionalValue(japan=0x803E9D34)  # s32/u32 frame counter used for parity/once-per-frame gates

    # ── Scalars (absolute addresses) ──────────────────────────────────────────────
    X_ADDRESS: int                 = RegionalValue(japan=0x803D78FC)
    Y_ADDRESS: int                 = RegionalValue(japan=0x803D7900)
    Z_ADDRESS: int                 = RegionalValue(japan=0x803D7904)

    # Math
    SIN_TABLE_PTR: int             = RegionalValue(japan=0x803eae28)
    COS_TABLE_PTR: int             = RegionalValue(japan=0x803eae2C)
    # In-game “actual speed” (pointer + offset pattern used historically)
    ACTUAL_SPEED_POINTER: int  = RegionalValue(japan=0x803B02E4)
    ACTUAL_SPEED_ADDRESS_OFFSET: int    = RegionalValue(japan=0x00000444)  # +0x444 from the dereferenced base

    # THE player base pointer: derefs to Link's fopAc_ac_c / daPy_lk_c class base,
    # so decomp class offsets apply to it unadjusted. Verified live on GZLJ01
    # 2026-08-20: deref + ACTOR_XYZ_OFFSET (0x1F8) held 800.947815, matching the
    # Link position global exactly, and deref + raw decomp offsets reproduced
    # tools/dolphin_mem.py's target_angle / travel_angle / msd / potential_speed.
    # Not named in the decomp; it sits at g_dComIfG_gameInfo + 0x5808.
    #
    # NOTE: a second global, 0x803AD860, derefs 0xD8 FURTHER INTO the same object
    # (delta verified constant at 0xD8 across four savestates). It is not the actor
    # base, so offsets measured against it are (decomp offset - 0xD8). Several older
    # scripts and tools/dolphin_mem.py entries still use it; prefer this pointer.
    PLAYER_POINTER: int                    = RegionalValue(japan=0x803BD910)

    # Animation fields (relative to Link base)
    ANIMATION_LENGTH: int               = RegionalValue(japan=0x00003034)
    ANIMATION_INCREMENT_OFFSET: int     = RegionalValue(japan=0x00003038)
    ANIMATION_POS_OFFSET: int           = RegionalValue(japan=0x0000303C)

    # Link’s state field (relative to Link base)
    PLAYER_STATE: int                    = RegionalValue(japan=0x000031D8)

    # Player position fields (relative to PLAYER_POINTER / the daPy_lk_c base)
    PLAYER_TARGET_FACING_OFFSET: int     = RegionalValue(japan=0x00034E8)  # s16 m34E8
    PLAYER_CURRENT_ANGLE_Y_OFFSET: int   = RegionalValue(japan=0x00000206)  # s16 current.angle.y
    PLAYER_POTENTIAL_SPEED_OFFSET: int   = RegionalValue(japan=0x000035BC)  # f32 mNormalSpeed
    
    # Player stick info. mStickDistance (0x35B0) is the value the swim/land procs
    # actually gate on; the 0x35B4 field beside it (m35B4) is a copy that lags by a
    # frame -- see tools/dolphin_mem.py's "msd" vs "stick_distance" entries.
    PLAYER_STICK_DISTANCE_OFFSET: int   = RegionalValue(japan=0x000035B0) # f32 mStickDistance
    STICK_DISTANCE_OFFSET: int          = RegionalValue(japan=0x000035B4) # f32 m35B4 (1-frame-late copy)
    
    # Equipent
    EQUIPPED_ITEM_Y: int                = RegionalValue(japan=0x803BDCD0)
    BOMB_COUNT: int                     = RegionalValue(japan=0x803B8172)

    # Wind waker
    CURRENT_BEAT_FRAME_OFFSET: int       = RegionalValue(japan=0x303C) # f32
    CURRENT_BEAT_OFFSET: int             = RegionalValue(japan=0x34D8) # u32
    
    # Controller inputs (raw, absolute)
    MAIN_STICK_X: int                   = RegionalValue(japan=0x803E4412)  # int8
    MAIN_STICK_Y: int                   = RegionalValue(japan=0x803E4413)  # int8
    CONTROLLER_INPUT: int               = RegionalValue(japan=0x803E0D2A)  # u16 buttons bitfield
    MAIN_STICK_ANGLE: int               = RegionalValue(japan=0x80398314)
    # Camera/CS angle pointer chain
    CSANGLE_BASE_PTR: int       = RegionalValue(japan=0x803AD380)  # u32 *
    CSANGLE_PTR_OFFSET: int     = RegionalValue(japan=0x00000034)  # +0x34, u32 *
    CSANGLE_U16_OFFSET: int     = RegionalValue(japan=0x000002B0)  # +0x2B0, final u16 angle

    EVENT_MODE: int             = RegionalValue(japan=0x803BD3A2)

    # camera-stick derived float helpers (absolute, float layout)
    MAIN_STICK_X_FLOAT: int             = RegionalValue(japan=0x80398308)
    MAIN_STICK_Y_FLOAT: int             = RegionalValue(japan=0x8039830C)
    MAIN_STICK_VALUE_FLOAT: int         = RegionalValue(japan=0x80398310)
    MAIN_STICK_ANGLE: int               = RegionalValue(japan=0x80398314)  # (halfword representation lives elsewhere)

    # Collision
    COLLISION_POINTER: int              = RegionalValue(japan=0x803BDC40)  # u32 pointer to collision block
    COLLISION_OFFSET: int               = RegionalValue(japan=0x00000496)  # +0x496 → u16 flags

    # Actor list
    ACTOR_LIST_HEAD: int         = RegionalValue(japan=0x803654CC)  # pointer to head of zelda heap
    # Node layout
    ACTOR_NODE_NEXT_OFFSET: int  = RegionalValue(japan=0x00)
    ACTOR_NODE_GPTR_OFFSET: int  = RegionalValue(japan=0x0C)
    # fopACTg layout
    ACTOR_GPROC_ID_OFFSET: int   = RegionalValue(japan=0x08)

    # Actor offsets
    ACTOR_XYZ_OFFSET: int        = RegionalValue(japan=0x1F8)
    ACTOR_XYZ_SPEED_OFFSET: int  = RegionalValue(japan=0x220)
    ACTOR_SPEED_OFFSET: int      = RegionalValue(japan=0x254)
    ACTOR_XYZ_ANGLE_OFFSET: int  = RegionalValue(japan=0x20C)  # csXyz shape_angle (NOT current.angle)
    ACTOR_GRAVITY_OFFSET: int    = RegionalValue(japan=0x600)
    ACTOR_OLD_XYZ_OFFSET: int    = RegionalValue(japan=0x1E4)  # actor_place old
    # actor_place = { cXyz pos @ +0x00; csXyz angle @ +0x0C }, so current.angle
    # is ACTOR_XYZ_OFFSET + ACTOR_PLACE_ANGLE_OFFSET (0x204) and .y is +0x206.
    ACTOR_PLACE_ANGLE_OFFSET: int = RegionalValue(japan=0x00C)
    ACTOR_SCALE_OFFSET: int      = RegionalValue(japan=0x214)  # cXyz scale

    # ItemDrop offsets
    ITEMDROP_TYPE_OFFSET: int    = RegionalValue(japan=0x63A)

    # TBox offsets
    TBOX_LIGHTING_OFFSET: int    = RegionalValue(japan=0x3E8)

    # Boat/ship & crane
    SHIP_POINTER: int                  = RegionalValue(japan=0x803BDC50)
    SHIP_CRANE_POS_PTR_OFFSET: int     = RegionalValue(japan=0x434)
    SHIP_MODE_OFFSET: int              = RegionalValue(japan=0x34D)
    
    # GBA offsets
    DISCONNECT_FLAG_OFFSET: int        = RegionalValue(japan=0x641)
    GBA_INPUT_OFFSET: int              = RegionalValue(japan=0x672)#RegionalValue(japan=0x644)#RegionalValue(japan=0x672)
    GBA_UPLOAD_ACTION_OFFSET: int      = RegionalValue(japan=0x682)
    
    # Keese offsets
    KEESE_ACTION_OFFSET                = RegionalValue(japan=0x2D1) # u8
    KEESE_BEHAVIOR_OFFSET              = RegionalValue(japan=0x2D3) # u8
    KEESE_POS_MOVE_OFFSET              = RegionalValue(japan=0x2E8) # cXyz
    KEESE_CHK_PLYR_DIST_OFFSET         = RegionalValue(japan=0x30C) # u16
    KEESE_RND_UPDATE_POS_OFFSET        = RegionalValue(japan=0x30E) # u16
    KEESE_ACTION_TIMER_OFFSET          = RegionalValue(japan=0x310) # u16
    
    # ChuChu offsets
    CHU_ACTION_OFFSET                  = RegionalValue(japan=0x2F5) # u8
    # Stage
    CURRENT_STAGE: int                 = RegionalValue(japan=0x803BD23C)  # fixed 11-char ASCII string

    # InputBuffer
    INPUT_BUFFER: int                  = RegionalValue(japan=0x803E4410)

    # Engine globals
    GAME_INFO: int                     = RegionalValue(japan=0x803B8108)  # g_dComIfG_gameInfo
    ROOM_NO: int                       = RegionalValue(japan=0x803E9F48)  # u8 current room number
    # g_fopAcTg_Queue. ACTOR_LIST_HEAD above is the +0x04 head pointer.
    ACTOR_QUEUE_BASE: int              = RegionalValue(japan=0x803654C8)
    ROOM_STATUS_BASE: int              = RegionalValue(japan=0x803B1188)  # dStage_roomControl_c::mStatus[]
    ZONE_ARRAY_BASE: int               = RegionalValue(japan=0x803B88B0)  # dSv_info_c::mZone[]