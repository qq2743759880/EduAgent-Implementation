"use client";

import * as React from "react";
import { Slider as SliderPrimitive } from "@base-ui/react/slider";
import { cn } from "@/lib/utils";

function Slider({
  className,
  children,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn(
        "relative flex w-full touch-none items-center select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-slate-200"
      >
        <SliderPrimitive.Indicator
          data-slot="slider-indicator"
          className="absolute h-full bg-primary"
        />
      </SliderPrimitive.Track>
      {children ??
        (() => {
          const valueArr = Array.isArray(props.value) ? props.value : null;
          const defArr = Array.isArray(props.defaultValue) ? props.defaultValue : null;
          const count = valueArr?.length ?? defArr?.length ?? 1;
          return Array.from({ length: count }).map((_, i) => (
            <SliderPrimitive.Thumb
              key={i}
              data-slot="slider-thumb"
              index={i}
              className="block h-4 w-4 rounded-full border border-primary/60 bg-background shadow-sm ring-2 ring-transparent transition-colors focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/60"
            />
          ));
        })()}
    </SliderPrimitive.Root>
  );
}

export { Slider };
