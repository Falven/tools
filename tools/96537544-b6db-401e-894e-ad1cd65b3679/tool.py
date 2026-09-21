__all__ = ["new_tool_2"]


_TITLE = "The Road That Learned Our Names"

_POEM = """Before the town had lifted up its blinds,
the baker struck a match against the day.
A narrow gold unfastened from the dark
and settled on the flour like quiet snow.
Outside, the road, still wet with last night's rain,
held every window upside down again.

I carried bread, a notebook, and a coat,
a map whose creases crossed through empty fields.
My mother tucked a button in my palm,
blue as the cup she used when guests arrived.
For what comes loose, she said, and closed my hand.
The kettle kept on singing as I left.

Beyond the houses, gardens thinned to grass.
A scarecrow wore the posture of a king
who'd given up his kingdom for the birds.
They gathered on his sleeves without a bow.
The wind went taking lessons from the wheat,
then practiced what it learned against my face.

At noon I reached a bridge of fitted stones,
each one accepting what the others weighed.
Below, the river shouldered broken light
through reeds that nodded without keeping score.
I watched a leaf go turning out of sight,
its little voyage needing none of mine.

An old man fished where shadows met the bank.
His line lay slack; his bucket held the sky.
He drew directions with a willow stick,
then rubbed a crooked turning smooth again.
The road is different since the flood, he said.
We stood a while beside his second map.

An orchard opened farther up the hill.
A woman balanced apples on her knees
and sorted summer into wooden crates.
She gave me one with weather on its skin.
The spotless ones are going into town.
This one's too sweet to spend its life being looked at.

I passed a school asleep behind its fence,
the swings still moving though the yard was bare.
A sum remained upon a classroom board,
unfinished where the teacher's chalk had snapped.
Beyond the glass, two swallows crossed the roof
and left no answer anyone could keep.

By evening I had found the railway line.
The station clock was seven minutes slow.
A porter wound it gently with a key,
as though the hours were something he could hurt.
He let me wait beside the little stove
while distant wheels grew louder through the rain.

The city rose in terraces of sound:
a cartwheel, bells, a quarrel, someone's song.
Above a shop, a girl shook out a sheet;
for half a breath a white field filled the street.
Then windows, bricks, and wires returned to place,
and ordinary traffic carried on.

I rented space beneath a sloping roof.
The landlady brought blankets, then a bowl
whose painted rim was worn to almost white.
Her husband made it forty years before.
She turned the chipped side gently toward the wall
but left the bowl where both my hands could reach.

All morning rain assembled on the roofs
and hurried down the gutters into drains.
Inside a shelter strangers shifted close
to give a soaked apprentice room to stand.
He held a paper parcel to his chest;
his shoes had lost their argument with water.

A fiddler played beneath the market arch.
One string was gone; the other three went on.
His open case contained a pear, two coins,
and someone's note with nothing on the back.
When children stopped, he changed the tune for them.
The smallest danced before she learned to smile.

That night I tried to write what I had seen.
I wrote the river, crossed the river out,
described a roof, then filled a page with rain.
At last I drew the bowl beside my bed,
its little chip, its ring of faded leaves,
and sent that home without explaining why.

The road bent seaward after several days.
Salt gathered on the buckles of my pack.
The fields grew short; the trees leaned all one way.
I heard the harbor long before it showed:
the knock of wood, the crying of the gulls,
a hammer giving shape to something broken.

Along the quay, a sailmaker stitched cloth
with hands that bore the memory of rope.
He pulled each length of thread against his thumb
and held the seam between himself and light.
A sail must carry more than wind, he said,
then asked if I could hold the other end.

I stayed to help him fold the heavy sheet.
By dusk the lamps were lit along the pier.
We ate our supper from a single pan
while thunder moved the furniture of heaven.
He paused and set another place for one
whose boat was late returning with the tide.

The storm arrived before the dishes dried.
It shook the latch and shouldered at the door.
Downstairs, the sea came nosing through the cracks.
We carried chairs and blankets up the steps,
then crossed the landing to an older neighbor
who would not leave without her sleeping cat.

All night the house contained our borrowed lives:
wet boots, a cage, three children, someone's bread.
A woman counted slowly through the thunder.
A boy pretended not to need her hand.
We passed the blankets, making room by inches,
and listened for the stair below the water.

At dawn the harbor wore a different shape.
One shed was gone; a dinghy blocked the lane.
The missing sailor knocked against the door,
too tired to tell the story more than once.
The sailmaker said nothing, fetched a towel,
and put the kettle where the flame could find it.

For days we worked at putting things to rights.
We lifted swollen drawers into the sun,
found spoons in gardens, swept the schoolhouse floor.
Some losses would not answer to a broom.
Beside a wall, a woman washed a photograph
and laid it faceup on her only chair.

When I moved on, the road was thick with leaves.
The orchard had surrendered all its fruit.
I recognized the gate, the leaning fence,
but not the quiet standing in the rows.
A ladder rested flat against the earth.
I stepped around it, careful of the rungs.

The fisherman was absent from the bridge.
His willow map had vanished in the grass.
I leaned above the water as before
and saw my face break softly into rings.
Somewhere upstream a branch had touched the current.
The river brought the news without the branch.

At home my mother opened up the door
before my lifted hand could reach the wood.
Her cup stood waiting by the kitchen stove.
I put the little button on the table.
She laughed: You found no use for it at all?
Then showed me where her cuff had lost its blue.

We stitched it on. Outside, the evening road
grew indistinct between the garden walls.
I named the people she had never met
until their chairs seemed gathered close to ours.
And when the bread came warm into my hands,
I broke it slowly, making room for more."""


def new_tool_2() -> dict[str, str | int]:
    """Return an original long poem, 'The Road That Learned Our Names'.

    Call with no arguments to receive a complete, prewritten English narrative
    poem about a journey, hospitality, and returning home: 24 six-line stanzas
    (144 nonblank lines). Returns title, poem (plain text with blank lines
    between stanzas), stanza_count, line_count, and word_count (whitespace-
    separated words in the poem, excluding the title).

    The text is identical on every call, not newly composed per request.
    No external services, credentials, dependencies, or file writes are needed.
    """
    return {
        "title": _TITLE,
        "poem": _POEM,
        "stanza_count": len(_POEM.split("\n\n")),
        "line_count": sum(bool(line.strip()) for line in _POEM.splitlines()),
        "word_count": len(_POEM.split()),
    }
