/** The demo's three situations in their order (D67, proposed; engine.tick.DEMO_ORDER): the normal one, an
 * unplanned closure and an investment. Each is a scenario of the simulator; keys 1, 2 and 3 choose them. */
export const SITUATIONS = [0, 4, 3] as const
export type Situation = (typeof SITUATIONS)[number]
