__all__ = ["get_simple_long_poem"]


_POEM = """A Day of Small Things

The morning sun climbs soft and slow,
And wakes the fields with golden glow.
I open up the door to see
The world that waits outside for me.

The grass is wet beneath my feet,
The air is cool, the apples sweet.
A little bird upon the wall
Sings out as if to greet us all.

I take a path beside the lane,
Still marked by last night's gentle rain.
A puddle holds a piece of sky,
And keeps a cloud as it goes by.

The baker sets his bread in rows,
A warm smell follows where he goes.
He waves a flour-covered hand
And says the day is looking grand.

An old dog sleeps beside a gate;
The morning work can surely wait.
He lifts his head to watch me pass,
Then settles deeper in the grass.

Two children race across the green,
The fastest feet I've ever seen.
They laugh and let their ribbons fly,
Like bits of rainbow in the sky.

I stop beside a small, clear stream
That shines as brightly as a dream.
It slips around each root and stone
And makes a music of its own.

A paper boat comes sailing through,
Its folded sail is painted blue.
It tips, then finds its way once more,
And floats toward the farther shore.

Beyond the bridge, a farmer sows
Small seeds in long and careful rows.
He trusts the rain, he trusts the light,
And leaves them resting out of sight.

I think of all the things that grow
Too deep and small for us to know:
A root, a hope, a quiet plan,
A wish to help the best we can.

At noon I find a shady tree
With room enough for more than me.
I eat my bread, then sit and rest,
While sparrows build a tiny nest.

A beetle walks across my shoe,
Then hurries on with work to do.
It does not know my name or care;
We simply share the summer air.

A cloud rolls in, the sky turns gray,
And sudden raindrops come to play.
They tap the leaves and fill the lane,
Then leave the whole world clean again.

I wait inside a little shed
And hear the rain above my head.
A stranger joins me with a smile;
We watch the road and talk a while.

We speak of gardens, cats, and tea,
Of all the places we might see.
The rain soon fades to drops of light,
And every leaf is fresh and bright.

I take the longer pathway home
Past fields where cows and horses roam.
The hills are green, the road is wide,
And evening settles at my side.

At home, warm light spills through the door,
My muddy shoes stay on the floor.
The kettle sings, the table's spread,
With bowls of soup and fresh-cut bread.

We talk about the day gone by,
The little boat, the changing sky.
The little things we saw and heard
Come back to life with every word.

Outside, the stars begin to peep,
The tired town falls fast asleep.
The moon looks down on roof and tree,
And lights the window next to me.

I close my eyes and softly say,
"Thank you for this simple day."
Then rest, and let the wide world turn
With more to love and more to learn.
"""


def get_simple_long_poem() -> str:
    """Return a long, original poem in simple English, with no input required.

    The fixed poem, "A Day of Small Things", follows an ordinary day from
    sunrise to bedtime in 20 four-line stanzas (80 verse lines). Returns plain
    text with the title and stanza breaks preserved. Uses no external services.
    """
    return _POEM
