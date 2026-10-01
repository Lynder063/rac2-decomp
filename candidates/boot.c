typedef float f32;
typedef int s32;
typedef unsigned char u8;

typedef struct {
    char pad0[0x8];
    int unk08;
    int *unk0C;
    char pad10[0x38];
    short unk48;
    short unk4A;
    char pad4C[0x4];
    int unk50;
    int unk54;
    int w;
    int h;
    int flags;
    char pad64[0x8];
    int unk6C;
    unsigned char cnt[4];
    int unk74;
    int unk78;
    int unk7C;
    void *unk80;
} HudElem;

typedef struct { int pos; int used; int size; } Ring;

typedef struct {
    char pad0[0x20];
    unsigned char state;
} Level16VendorMoby;

extern void *D_00133E74;
extern void *D_0013A308;
extern unsigned char D_00137E00;

struct IndirectWord
{
    unsigned char reserved[64];
    unsigned int *value;
};

void *FUN_00115200(void)
{
    return D_00133E74;
}

void **FUN_00115210(void)
{
    return &D_0013A308;
}

void FUN_00120BC8(void)
{
}

void *FUN_00125960(void)
{
    return &D_00137E00;
}

unsigned int FUN_0012F9A8(struct IndirectWord *resource)
{
    return *resource->value;
}

unsigned int FUN_0026F710(void)
{
    return 0;
}

void FUN_0026F718(void)
{
}

int FUN_0028B740(HudElem *rec, int *x, int *y) {
    int w = rec->w;
    int h = rec->h;
    int flags = rec->flags;

    if ((flags ^ 1) & 1) {
        if (!(flags & 2)) {
            *y -= h >> 1;
        }
    }
    if (!(rec->flags & 4)) {
        if (rec->flags & 8) {
            *x -= w;
        } else {
            *x -= w >> 1;
        }
    }
    return 0;
}

float FUN_002A7AA8(float a, float b, float c, float d, float t) {
    float p = (d - c) - (a - b);
    float q = (a - b) - p;
    float t2 = t * t;
    float t3 = t2 * t;
    return p * t3 + q * t2 + (c - a) * t + b;
}

int FUN_002A8860(int *p, int b) {
    int w = *p;
    int v = (w >> 24) - b;
    if (v < 0) v = 0;
    *p = (w & 0xFFFFFF) | (v << 24);
    return v == 0;
}

int FUN_002A8AF0(float *p, float *v, int n) {
    int r = 0;
    int i = 0;
    int k;
    for (k = 0; k < n; k++) {
        float y1 = v[k * 4 + 1];
        i++;
        if (i == n) i = 0;
        if ((y1 < p[1] && p[1] <= v[i * 4 + 1]) || (v[i * 4 + 1] < p[1] && p[1] <= y1)) {
            if (v[k * 4] + (p[1] - v[k * 4 + 1]) / (v[i * 4 + 1] - v[k * 4 + 1]) * (v[i * 4] - v[k * 4]) < p[0]) {
                r = !r;
            }
        }
    }
    return r;
}

f32 FUN_002AA140(f32 a, f32 b, f32 t) { return a + (b - a) * t; }

void FUN_002AAF40(int *a, int *b, int *c, int mask) {
    int x, y;
    if (mask & 1) { x = *b; y = *a; *a = x; *b = y; }
    if (mask & 2) { x = *c; y = *b; *b = x; *c = y; }
    if (mask & 4) { x = *a; y = *c; *c = x; *a = y; }
}

s32 FUN_002CC6A0(u8 *p) { *(s32 *)(p + 0x44) = -1; return 0; }

int FUN_00312B58(Level16VendorMoby *moby) {
    return moby->state == 6;
}

int FUN_00312E10(unsigned char *p) { return p[0x20] == 1; }

void FUN_003505E0(char *base, int n) {
    Ring *r = (Ring *)(base + 0x50000);
    int avail = r->size - r->used;
    if (n < avail) avail = n;
    r->pos = (r->pos + avail) % r->size;
    r->used += avail;
}
