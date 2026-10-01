#ifndef MOBY_H
#define MOBY_H

#include "common.h"

/*
 * Moby Instance Structure for Ratchet & Clank 2 (Going Commando).
 *
 * Reconstructed from:
 *   - Discord community research (#rac-ps2-reverse-engineering, @creepnt 2021-2023)
 *   - Deadlocked / UYA shared engine structures (first 0x28 bytes match MobyInstance)
 *   - Retail string references and assertions in SCUS_972.68
 */

struct Moby;

typedef void (*MobyUpdateFunc)(struct Moby *moby);

/*
 * Moby modeBits flags (subset known):
 *   0x40 - No pre-update
 */
#define MOBY_MODE_NO_PRE_UPDATE        0x40

/*
 * Known Moby Class IDs (oClass):
 *   4351 - Debug "clank-switch" trigger moby (G34, @creepnt 2021)
 */
#define MOBY_OCLASS_DEBUG_CLANK_SWITCH 4351

/*
 * Moby Update Dispatch:
 *   Vita port leak (C:\projects\RCVita\RC_Vita\rc2\code\game\boot.cpp) confirms
 *   an update table with 8192 entries indexed across loaded actors.
 */
#define MOBY_UPDATE_TABLE_CAPACITY     8192

typedef struct Moby {
    /* 0x00 - 0x28: Common Insomniac Moby header */
    f32 position[3];       /* 0x00: World position X, Y, Z */
    u8  state;             /* 0x0C: Moby state */
    u8  group;             /* 0x0D: Collision / grouping index */
    u8  mclass;            /* 0x0E: Moby class sub-identifier */
    u8  alpha;             /* 0x0F: Opacity / blend alpha */
    
    f32 rotation[3];       /* 0x10: Euler angles / orientation Pitch, Yaw, Roll */
    u8  scale;             /* 0x1C: Uniform scale */
    u8  drawDistance;      /* 0x1D: Max render distance multiplier */
    u16 modeBits;          /* 0x1E: Behavioral mode flags (e.g. 0x40 = no pre-update) */
    
    void *pModel;          /* 0x20: Pointer to 3D model geometry / visual asset */
    void *pParent;         /* 0x24: Pointer to parent moby or joint node */
    
    u8   pad28[0x3C];      /* 0x28 - 0x64: Animation, collision pill, matrix cache */
    
    /* 0x64: Per-moby function pointers and variables */
    MobyUpdateFunc pUpdate;/* 0x64: Per-frame update function pointer */
    void          *pVar;   /* 0x68: Pointer to moby-specific state/pVars struct */
    
    s16  oClass;           /* 0x6C: Object class ID (e.g. oClass 4351) */
    s16  UID;              /* 0x6E: Unique instance identifier in level */
} Moby;

/* Core engine moby management APIs */
void CreateMobyChain(void);
void PreUpdateMoby(Moby *moby);
void PostUpdateMoby(Moby *moby);

#endif /* MOBY_H */
